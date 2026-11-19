"""本地混合检索（ARCHITECTURE §4）：BM25 + TF-IDF，零外部 Embedding。

输入问题 → 分词 → 对 chunks 表稀疏向量打分 → 混合排序 → Top-K。
每个命中携带 doc_id / source_file / heading_path / para_id（溯源四件套）。

多实体问题召回：问句按标点/连接词分解为子查询（每个实体单独检索），
RRF（Reciprocal Rank Fusion）融合排序——保证跨文档对比类问题中
每个实体文档都有段落进入 Top-K（通用机制，非特定问题适配）。
"""
from __future__ import annotations

import json
import math
import re

from .db import get_conn

_TOKEN_RE = re.compile(r"[一-鿿]+|[a-zA-Z0-9]+")

# 多实体分解：句子级切分（标点）+ 实体连接词
_SPLIT_RE = re.compile(r"[。；;！!？?\n]+|和|与|以及|还是|跟")
# 通用疑问功能词（剥离用；不含任何领域实体）
_QUE_WORDS = [
    "是谁", "是多少", "是什么", "有多少", "哪些", "哪家", "哪个", "何时",
    "怎么", "如何", "为什么", "多少", "什么意思", "有没有", "能不能",
    "呢", "吗", "的", "了",
]


def _strip_que_words(frag: str) -> str:
    s = frag
    changed = True
    while changed:
        changed = False
        for w in _QUE_WORDS:
            if s.startswith(w):
                s, changed = s[len(w):], True
            elif s.endswith(w):
                s, changed = s[: -len(w)], True
    return s.strip()


def split_subqueries(question: str, *, max_subs: int = 4) -> list[str]:
    """把多实体问题分解为子查询（实体短语级，剥离疑问功能词）。

    例："A 是谁？B 做了什么？" → ["A", "B 做了什么"（剥疑问词后）...]。
    剥离后仍 ≥2 字符的片段才保留（单字/空片段无检索价值）；
    无分解价值时返回空列表（单查询路径行为完全不变）。
    """
    parts = []
    for raw in _SPLIT_RE.split(question or ""):
        frag = _strip_que_words(raw.strip())
        if len(frag) >= 2 and frag != (question or "").strip():
            parts.append(frag)
    # 真实问题通常在末尾（"……请问 X？"）：先保留最后一段再从头部填充，
    # 防止长干扰文本（注入段落）把真实问题挤出子查询窗口。
    if len(parts) > max_subs:
        parts = [parts[-1]] + parts[: max_subs - 1]
    return parts[:max_subs]


def tokenize(text: str) -> list[str]:
    """中文 CJK bigram + 英文/数字整词（与 ingestion.tokenize 同源）。"""
    tokens: list[str] = []
    for m in _TOKEN_RE.finditer(text or ""):
        s = m.group()
        if re.match(r"^[一-鿿]+$", s):
            if len(s) <= 2:
                tokens.append(s)
            else:
                for i in range(len(s) - 1):
                    tokens.append(s[i : i + 2])
        else:
            tokens.append(s)
    return tokens


def _bm25_score(tf: dict, dl: int, avg_dl: float, k1: float = 1.5, b: float = 0.75) -> float:
    s = 0.0
    for term, tfq in tf.items():
        denom = tfq + k1 * (1 - b + b * (dl / avg_dl if avg_dl > 0 else 1.0))
        s += tfq * (k1 + 1) / max(denom, 1e-9)
    return s


def rare_term_queries(question: str, *, max_extra: int = 4) -> list[str]:
    """从问题中抽出稀有实体词（语料 df 最低的几个词项）单独成查询。

    通用查询精化（term-importance query refinement）：人名/职位/机构简称等
    稀有词在长句中会被常用 bigram 的得分淹没；把它们拎出来做精确查找，
    保证证据段落（如领导层表里的 CTO、聘任讲话里的"原 CTO"）能进候选池。
    排除纯数字/纯疑问词/单字噪声；无稀有词时返回空列表。
    """
    toks = tokenize(question)
    if not toks:
        return []
    with get_conn() as conn:
        rows = conn.execute("SELECT bm25_vec FROM chunks").fetchall()
        if not rows:
            return []
        n_chunks = len(rows)
        df: dict[str, int] = {}
        for r in rows:
            for t in json.loads(r["bm25_vec"] or "{}"):
                df[t] = df.get(t, 0) + 1
        # 稀有度：df 升序；只取语料中确实存在（df>0）的词
        # 稀有度 × 位置权重：真实问题通常在问句末尾（前部可能是干扰文本），
        # 位置越靠后权重越高；纯 df 排序会让干扰段词汇抢占证据槽位。
        last_pos: dict[str, int] = {}
        for i, t in enumerate(toks):
            last_pos[t] = i
        n_tok = max(len(toks), 1)

        def _priority(t: str) -> float:
            # ASCII 术语（CTO/CEO/BM25 等）是强实体信号，恒定高优先
            if t.isascii():
                return df[t] * 0.1
            pos_w = 0.5 + last_pos.get(t, 0) / n_tok  # 0.5–1.5
            return df[t] / pos_w

        rare = sorted({t for t in toks if df.get(t, 0) > 0}, key=_priority)
        picked: list[str] = []
        for t in rare:
            if len(picked) >= max_extra:
                break
            # 过滤噪声：纯数字、单字、含疑问/功能字的 bigram
            if t.isdigit() or len(t) < 2:
                continue
            if any(w in t for w in _QUE_WORDS):
                continue
            if any(c in t for c in "是不出请他她它你我吗呢啊吧"):
                continue
            if df[t] > max(1, int(n_chunks * 0.03)):
                break  # 已不稀有，后面的更常见，停止
            picked.append(t)
        if not picked:
            return []
    # 每个稀有词单独成查询（组合查询会让高频共现段落挤掉单词证据段）
    return picked


def _rank_one(question: str, *, top_n: int) -> list[dict]:
    """单查询打分：BM25+TF-IDF 混合，返回按分数降序的候选列表。

    BM25 采用标准分解：入库端存文档侧饱和 tf 权重（idf 置 1，见
    ingestion.bm25_weights 注释"语料级修正由检索端混合时处理"），
    查询端乘语料级 idf 与查询词频——此前实现漏接了 idf 一级，
    稀有实体词（人名/职位/机构简称）与常用词等权，导致多实体对比类
    查询召回失衡。这里补齐为教科书 BM25：
      score(q,d) = Σ_t idf(t) · qtf_cap(t) · W_doc(t)
      idf(t)     = ln(1 + (N - df_t + 0.5) / (df_t + 0.5))   （Lucene 形式，非负）
    """
    qtokens = tokenize(question)
    if not qtokens:
        return []
    qtf: dict[str, int] = {}
    for t in qtokens:
        qtf[t] = qtf.get(t, 0) + 1

    with get_conn() as conn:
        # JOIN documents 补齐溯源四件套中的 doc_title / source_file（引用卡片展示用）
        rows = conn.execute(
            "SELECT c.doc_id, c.para_id, c.heading_path, c.block_type, c.text, c.chars,"
            " c.bm25_vec, c.tfidf_vec, d.title AS doc_title, d.source_file"
            " FROM chunks c JOIN documents d ON d.doc_id = c.doc_id"
        ).fetchall()
        if not rows:
            return []
        # 语料级 df 统计 → idf（Lucene 非负形式；N = chunk 总数）
        n_chunks = len(rows)
        df: dict[str, int] = {}
        for r in rows:
            for t in json.loads(r["bm25_vec"] or "{}"):
                df[t] = df.get(t, 0) + 1
        idf = {
            t: math.log(1 + (n_chunks - c + 0.5) / (c + 0.5)) for t, c in df.items()
        }

        scored = []
        for r in rows:
            d_bm = json.loads(r["bm25_vec"] or "{}")
            d_tf = json.loads(r["tfidf_vec"] or "{}")
            # BM25：文档侧存储权重 × 语料级 idf × 查询词频（cap 3 防重复词主导）
            bm = sum(
                idf.get(t, 0.0) * d_bm.get(t, 0.0) * min(f, 3)
                for t, f in qtf.items()
            )
            # TF-IDF：问题词项的 tfidf 权重之和（入库端已含 idf）
            tfv = sum(d_tf.get(t, 0.0) * min(f, 3) for t, f in qtf.items())
            # 归一化后混合
            score = 0.6 * bm + 0.4 * tfv
            if score > 0:
                scored.append(
                    {
                        "doc_id": r["doc_id"],
                        "doc_title": r["doc_title"],
                        "source_file": r["source_file"],
                        "para_id": r["para_id"],
                        "heading_path": r["heading_path"],
                        "block_type": r["block_type"],
                        "text": r["text"],
                        "chars": r["chars"],
                        "score": round(score, 6),
                    }
                )
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_n]


def hybrid_search(question: str, *, top_k: int = 5) -> list[dict]:
    """混合检索：0.6 * BM25 + 0.4 * TF-IDF；多实体问题 RRF 融合子查询。

    返回带溯源的 Top-K；score 归一化到 0-1（供引用卡片展示）。
    """
    if not question or not question.strip():
        return []
    subs = split_subqueries(question)
    rare = rare_term_queries(question)
    per_query = [question] + subs
    lists = [_rank_one(q, top_n=max(top_k * 3, 10)) for q in per_query if q]
    rare_lists = [_rank_one(q, top_n=max(top_k * 3, 10)) for q in rare]

    if not any(lists):
        return []

    # 候选池：全部查询（含稀有词精化）的最大归一化分 + 多查询共现加成。
    # 稀有词查询的 rank-1 证据段（领导层表、聘任讲话等）因此获得高分入场资格。
    pool: dict[str, dict] = {}
    for lst in lists + rare_lists:
        if not lst:
            continue
        mx = max(x["score"] for x in lst) or 1.0
        for h in lst:
            e = pool.setdefault(h["para_id"], {**h, "_s": 0.0, "_n": 0})
            e["_s"] = max(e["_s"], h["score"] / mx)
            e["_n"] += 1
    cands = sorted(pool.values(), key=lambda x: (x["_s"] + 0.05 * (x["_n"] - 1)), reverse=True)

    if len(subs) == 0:
        # 单查询路径：候选池排序（含稀有词加成）取 Top-K
        top = cands[:top_k]
    else:
        # 多查询选择（保底槽位优先级）：
        # ①稀有词查询的 rank-1 证据段最优先（领导层表/价值观/聘任讲话类
        #   短段落极易被概览段挤掉，而它们恰是事实题的证据所在）；
        # ②主查询与每个实体子查询的 rank-1 段落保底（跨文档实体覆盖）；
        # ③剩余槽位按候选池分数（含共现/稀有词加成）降序填充。
        top = []
        seen: set[str] = set()

        seen_docs: set[str] = set()

        def _take(h, dedup_doc=False):
            if len(top) >= top_k or h["para_id"] in seen:
                return
            if dedup_doc and h["doc_id"] in seen_docs:
                return
            seen.add(h["para_id"])
            seen_docs.add(h["doc_id"])
            top.append(h)

        # 保底轮转（每槽取一个未占用文档的证据段）：
        #   队列 = [主查询] + 稀有词查询 + 实体子查询，轮转推进；
        #   每个队列从自己的 rank-1 往下找第一个"文档未被保底"的段落
        #   （主查询 rank-2 常是跨文档的另一实体证据，如晚报报道段）。
        # 已保底文档的段落仍可经池分数填充剩余槽位。
        queues = [lists[:1], rare_lists, lists[1:]]
        cursors = [[0] * len(q) for q in queues]
        turn = 0
        guard = 0
        while len(top) < top_k and guard < 64:
            guard += 1
            advanced = False
            for k in range(len(queues)):
                idx = (turn + k) % len(queues)
                q_list, cur = queues[idx], cursors[idx]
                for qi, lst in enumerate(q_list):
                    while cur[qi] < len(lst):
                        h = pool[lst[cur[qi]]["para_id"]]
                        cur[qi] += 1
                        if h["doc_id"] not in seen_docs:
                            _take(h, dedup_doc=True)
                            advanced = True
                            break
                    if advanced:
                        break
                if advanced:
                    break
            if not advanced:
                break
            turn = (turn + 1) % len(queues)
        for h in cands:
            if len(top) >= top_k:
                break
            if h["para_id"] not in seen:
                seen.add(h["para_id"])
                top.append(h)
    for x in top:
        x["score"] = x.get("_s", x["score"])
    # 输出顺序契约：按相关性分数降序（选择机制决定集合，排序决定次序）
    top.sort(key=lambda x: x["score"], reverse=True)

    # 分数归一化到 0-1
    mx = max((x["score"] for x in top), default=1.0) or 1.0
    for x in top:
        x["score"] = round(x["score"] / mx, 4)
    return top


def source_file_of(conn, doc_id: str) -> str:
    row = conn.execute(
        "SELECT source_file FROM documents WHERE doc_id = ?", (doc_id,)
    ).fetchone()
    return row["source_file"] if row else doc_id
