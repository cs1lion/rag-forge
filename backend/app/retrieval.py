"""本地混合检索引擎（P1 进化版）：SQLite FTS5 BM25 + 可选本地稠密向量 + RRF 融合。

彻底消除旧版每次子查询全表扫描 + 双次 `json.loads` 的 O(N) 瓶颈：
1. 词法通道直接走 SQLite C 层 `chunks_fts` 倒排索引 + 内置 `bm25()`；
2. 语义通道按需读取 `chunks.embedding`（支持 sqlite-vec 或零依赖余弦相似度）；
3. 用 Reciprocal Rank Fusion (RRF) 融合多实体子查询、稀有词查询与语义通道，
   保留原有单文档至多 2 段多样性约束，并输出 `score_breakdown` 供前端 X-Ray 透视。
"""
from __future__ import annotations

import json
import math
import re

from .config import settings
from .db import get_conn
from .embeddings import cosine_similarity, embed_texts, unpack_vector

_TOKEN_RE = re.compile(r"[一-龥]+|[a-zA-Z0-9]+")
_SPLIT_RE = re.compile(r"[。；;！？?\n]+|和|与|以及|还是|跟")
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
    parts = []
    for raw in _SPLIT_RE.split(question or ""):
        frag = _strip_que_words(raw.strip())
        if len(frag) >= 2 and frag != (question or "").strip():
            parts.append(frag)
    if len(parts) > max_subs:
        parts = [parts[-1]] + parts[: max_subs - 1]
    return parts[:max_subs]


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for m in _TOKEN_RE.finditer(text or ""):
        s = m.group()
        if re.match(r"^[一-龥]+$", s):
            if len(s) <= 2:
                tokens.append(s)
            else:
                for i in range(len(s) - 1):
                    tokens.append(s[i : i + 2])
        else:
            tokens.append(s.lower())
    return tokens


def _fts_or_query(tokens: list[str]) -> str:
    """构造安全的 FTS5 OR 查询串（去重 + 双引号转义防语法注入）。"""
    uniq: list[str] = []
    seen: set[str] = set()
    for t in tokens:
        clean = t.replace('"', "").strip()
        if clean and clean not in seen:
            seen.add(clean)
            uniq.append(f'"{clean}"')
    return " OR ".join(uniq[:32])


def _row_to_hit(r, score: float, *, fts_score: float = 0.0, vec_score: float = 0.0) -> dict:
    return {
        "doc_id": r["doc_id"],
        "doc_title": r["doc_title"],
        "source_file": r["source_file"],
        "para_id": r["para_id"],
        "heading_path": r["heading_path"],
        "block_type": r["block_type"],
        "text": r["text"],
        "chars": r["chars"],
        "injection_flag": r["injection_flag"],
        "risk_warning": r["risk_warning"],
        "score": round(score, 6),
        "score_breakdown": {
            "fts": round(fts_score, 6),
            "vector": round(vec_score, 6),
            "rrf": 0.0,
        },
    }


def _rank_fts5(
    question: str,
    *,
    top_n: int,
    doc_ids: list[str] | None = None,
    db_path=None,
) -> list[dict]:
    """O(log N) SQLite FTS5 倒排索引 BM25 召回。"""
    qtokens = tokenize(question)
    if not qtokens:
        return []
    match_expr = _fts_or_query(qtokens)
    if not match_expr:
        return []

    with get_conn(db_path) as conn:
        fts_count = conn.execute("SELECT COUNT(*) AS n FROM chunks_fts").fetchone()["n"]
        if fts_count == 0:
            return _rank_legacy_json(question, top_n=top_n, doc_ids=doc_ids, db_path=db_path)

        sql = (
            "SELECT c.doc_id, c.para_id, c.heading_path, c.block_type, c.text, c.chars,"
            " d.title AS doc_title, d.source_file, d.injection_flag, d.risk_warning,"
            " -bm25(chunks_fts) AS fts_score"
            " FROM chunks_fts"
            " JOIN chunks c ON c.para_id = chunks_fts.para_id"
            " JOIN documents d ON d.doc_id = c.doc_id"
            " WHERE chunks_fts MATCH ?"
        )
        params: list = [match_expr]
        if doc_ids:
            placeholders = ",".join("?" * len(doc_ids))
            sql += f" AND c.doc_id IN ({placeholders})"
            params.extend(doc_ids)
        sql += " ORDER BY fts_score DESC LIMIT ?"
        params.append(top_n)
        rows = conn.execute(sql, params).fetchall()

    hits: list[dict] = []
    for r in rows:
        raw_s = max(float(r["fts_score"] or 0.0), 1e-6)
        hits.append(_row_to_hit(r, raw_s, fts_score=raw_s))
    return hits


def _rank_legacy_json(
    question: str,
    *,
    top_n: int,
    doc_ids: list[str] | None = None,
    db_path=None,
) -> list[dict]:
    """兜底回退：仅当旧测试直接 INSERT chunks 未走 FTS5 时触发。"""
    qtokens = tokenize(question)
    if not qtokens:
        return []
    qtf: dict[str, int] = {}
    for t in qtokens:
        qtf[t] = qtf.get(t, 0) + 1
    with get_conn(db_path) as conn:
        sql = (
            "SELECT c.doc_id, c.para_id, c.heading_path, c.block_type, c.text, c.chars,"
            " c.bm25_vec, c.tfidf_vec, d.title AS doc_title, d.source_file,"
            " d.injection_flag, d.risk_warning"
            " FROM chunks c JOIN documents d ON d.doc_id = c.doc_id"
        )
        params: list = []
        if doc_ids:
            placeholders = ",".join("?" * len(doc_ids))
            sql += f" WHERE c.doc_id IN ({placeholders})"
            params = list(doc_ids)
        rows = conn.execute(sql, params).fetchall()
        if not rows:
            return []
        n_chunks = len(rows)
        df: dict[str, int] = {}
        for r in rows:
            for t in json.loads(r["bm25_vec"] or "{}"):
                df[t.lower()] = df.get(t.lower(), 0) + 1
        idf = {t: math.log(1 + (n_chunks - c + 0.5) / (c + 0.5)) for t, c in df.items()}
        scored = []
        for r in rows:
            d_bm = {k.lower(): v for k, v in json.loads(r["bm25_vec"] or "{}").items()}
            d_tf = {k.lower(): v for k, v in json.loads(r["tfidf_vec"] or "{}").items()}
            bm = sum(idf.get(t, 0.0) * d_bm.get(t, 0.0) * min(f, 3) for t, f in qtf.items())
            tfv = sum(d_tf.get(t, 0.0) * min(f, 3) for t, f in qtf.items())
            score = 0.6 * bm + 0.4 * tfv
            if score > 0:
                scored.append(_row_to_hit(r, score, fts_score=score))
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_n]


def _rank_vector(
    question: str,
    *,
    top_n: int,
    doc_ids: list[str] | None = None,
    db_path=None,
) -> list[dict]:
    """语义向量通道：按需计算问题向量并检索带 embedding 的段落。"""
    qvecs = embed_texts([question])
    if not qvecs:
        return []
    qvec = qvecs[0]
    with get_conn(db_path) as conn:
        sql = (
            "SELECT c.doc_id, c.para_id, c.heading_path, c.block_type, c.text, c.chars,"
            " c.embedding, d.title AS doc_title, d.source_file,"
            " d.injection_flag, d.risk_warning"
            " FROM chunks c JOIN documents d ON d.doc_id = c.doc_id"
            " WHERE c.embedding IS NOT NULL"
        )
        params: list = []
        if doc_ids:
            placeholders = ",".join("?" * len(doc_ids))
            sql += f" AND c.doc_id IN ({placeholders})"
            params = list(doc_ids)
        rows = conn.execute(sql, params).fetchall()
    scored = []
    for r in rows:
        sim = cosine_similarity(qvec, unpack_vector(r["embedding"]))
        if sim > 0.15:
            scored.append(_row_to_hit(r, sim, vec_score=sim))
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_n]


def rare_term_queries(
    question: str, *, max_extra: int = 4, doc_ids: list[str] | None = None, db_path=None
) -> list[str]:
    """基于 FTS5 倒排统计快速抽取稀有实体词（不再全表反序列化 JSON）。"""
    toks = tokenize(question)
    if not toks:
        return []
    uniq_toks = list(dict.fromkeys(toks))
    with get_conn(db_path) as conn:
        if doc_ids:
            placeholders = ",".join("?" * len(doc_ids))
            n_chunks = conn.execute(
                f"SELECT COUNT(*) AS n FROM chunks WHERE doc_id IN ({placeholders})",
                doc_ids,
            ).fetchone()["n"]
        else:
            n_chunks = conn.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()["n"]
        if n_chunks == 0:
            return []
        fts_count = conn.execute("SELECT COUNT(*) AS n FROM chunks_fts").fetchone()["n"]
        if fts_count == 0:
            return []

        df: dict[str, int] = {}
        for t in uniq_toks:
            clean = t.replace('"', "").strip()
            if not clean:
                continue
            sql = "SELECT COUNT(*) AS n FROM chunks_fts WHERE chunks_fts MATCH ?"
            params: list = [f'"{clean}"']
            if doc_ids:
                placeholders = ",".join("?" * len(doc_ids))
                sql += f" AND doc_id IN ({placeholders})"
                params.extend(doc_ids)
            df[t] = conn.execute(sql, params).fetchone()["n"]

    last_pos = {t: i for i, t in enumerate(toks)}
    n_tok = max(len(toks), 1)

    def _priority(t: str) -> float:
        if t.isascii():
            return df[t] * 0.1
        pos_w = 0.5 + last_pos.get(t, 0) / n_tok
        return df[t] / pos_w

    rare = sorted({t for t in uniq_toks if df.get(t, 0) > 0}, key=_priority)
    picked: list[str] = []
    for t in rare:
        if len(picked) >= max_extra:
            break
        if t.isdigit() or len(t) < 2:
            continue
        if any(w in t for w in _QUE_WORDS):
            continue
        if any(c in t for c in "是不出请他她它你我吗呢啊吧"):
            continue
        if df[t] > max(1, int(n_chunks * 0.03)):
            break
        picked.append(t)
    return picked


def hybrid_search(
    question: str,
    *,
    top_k: int = 5,
    doc_ids: list[str] | None = None,
    db_path=None,
) -> list[dict]:
    """多路混合检索：FTS5 词法通道 + 可选语义向量通道 + RRF 无量纲融合 + 文档多样性保底。"""
    if not question or not question.strip():
        return []
    if doc_ids is not None and len(doc_ids) == 0:
        return []

    rrf_k = int(getattr(settings, "retrieval_rrf_k", 60))
    cand_depth = max(top_k * 4, 20)
    subs = split_subqueries(question)
    rare = rare_term_queries(question, doc_ids=doc_ids, db_path=db_path)

    ranked_lists: list[tuple[float, list[dict]]] = []
    main_fts = _rank_fts5(question, top_n=cand_depth, doc_ids=doc_ids, db_path=db_path)
    if main_fts:
        ranked_lists.append((1.0, main_fts))
    for sq in subs:
        lst = _rank_fts5(sq, top_n=cand_depth, doc_ids=doc_ids, db_path=db_path)
        if lst:
            ranked_lists.append((0.75, lst))
    for rq in rare:
        lst = _rank_fts5(rq, top_n=cand_depth, doc_ids=doc_ids, db_path=db_path)
        if lst:
            ranked_lists.append((0.65, lst))

    vec_hits = _rank_vector(question, top_n=cand_depth, doc_ids=doc_ids, db_path=db_path)
    if vec_hits:
        ranked_lists.append((1.0, vec_hits))

    if not ranked_lists:
        return []

    pool: dict[str, dict] = {}
    for weight, lst in ranked_lists:
        for rank, hit in enumerate(lst, start=1):
            pid = hit["para_id"]
            if pid not in pool:
                pool[pid] = {
                    **hit,
                    "score_breakdown": dict(hit["score_breakdown"]),
                    "_rrf": 0.0,
                }
            entry = pool[pid]
            entry["_rrf"] += weight / (rrf_k + rank)
            entry["score_breakdown"]["fts"] = max(
                entry["score_breakdown"]["fts"], hit["score_breakdown"]["fts"]
            )
            entry["score_breakdown"]["vector"] = max(
                entry["score_breakdown"]["vector"], hit["score_breakdown"]["vector"]
            )

    cands = sorted(pool.values(), key=lambda x: x["_rrf"], reverse=True)

    # 文档多样性约束：优先每文档最多 2 段，不足时放开
    top: list[dict] = []
    seen: set[str] = set()
    doc_count: dict[str, int] = {}

    def take(h: dict, *, max_per_doc: int | None = None) -> bool:
        if len(top) >= top_k or h["para_id"] in seen:
            return False
        if max_per_doc is not None and doc_count.get(h["doc_id"], 0) >= max_per_doc:
            return False
        seen.add(h["para_id"])
        doc_count[h["doc_id"]] = doc_count.get(h["doc_id"], 0) + 1
        top.append(h)
        return True

    for h in cands:
        if len(top) >= top_k:
            break
        take(h, max_per_doc=2)
    for h in cands:
        if len(top) >= top_k:
            break
        take(h)

    mx = max((x["_rrf"] for x in top), default=1.0) or 1.0
    out: list[dict] = []
    for x in top:
        rrf_val = x.pop("_rrf")
        x["score_breakdown"]["rrf"] = round(rrf_val, 6)
        x["score"] = round(rrf_val / mx, 4)
        out.append(x)
    out.sort(key=lambda x: x["score"], reverse=True)
    return out


def source_file_of(conn, doc_id: str) -> str:
    row = conn.execute(
        "SELECT source_file FROM documents WHERE doc_id = ?", (doc_id,)
    ).fetchone()
    return row["source_file"] if row else doc_id
