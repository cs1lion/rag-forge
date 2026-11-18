"""本地混合检索（ARCHITECTURE §4）：BM25 + TF-IDF，零外部 Embedding。

输入问题 → 分词 → 对 chunks 表稀疏向量打分 → 混合排序 → Top-K。
每个命中携带 doc_id / source_file / heading_path / para_id（溯源四件套）。
"""
from __future__ import annotations

import json
import math
import re

from .db import get_conn

_TOKEN_RE = re.compile(r"[一-鿿]+|[a-zA-Z0-9]+")


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


def hybrid_search(question: str, *, top_k: int = 5) -> list[dict]:
    """混合检索：0.6 * BM25 + 0.4 * TF-IDF，返回带溯源的 Top-K。"""
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
        # 语料级统计（与 ingestion 入库口径一致）
        doc_lens = [r["chars"] or 1 for r in rows]
        avg_dl = sum(doc_lens) / len(doc_lens)
        df: dict[str, int] = {}
        for r in rows:
            for t in json.loads(r["bm25_vec"] or "{}"):
                df[t] = df.get(t, 0) + 1
        n_docs = len(rows)
        idf = {t: math.log(1 + n_docs / (c + 1)) + 1 for t, c in df.items()}

        scored = []
        for r, dl in zip(rows, doc_lens):
            d_bm = json.loads(r["bm25_vec"] or "{}")
            d_tf = json.loads(r["tfidf_vec"] or "{}")
            # BM25：问题词项在文档中的权重 × 查询词频
            bm = sum(d_bm.get(t, 0.0) * f for t, f in qtf.items())
            bm = _bm25_score({t: d_bm.get(t, 0.0) * f for t, f in qtf.items()}, dl, avg_dl)
            # TF-IDF：问题词项的 tfidf 权重之和
            tfv = sum(d_tf.get(t, 0.0) * f for t, f in qtf.items())
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
                        "bm25": round(bm, 6),
                        "tfidf": round(tfv, 6),
                    }
                )
    scored.sort(key=lambda x: x["score"], reverse=True)
    top = scored[:top_k]
    # 分数归一化到 0-1（供引用卡片展示）
    mx = max((x["score"] for x in top), default=1.0) or 1.0
    for x in top:
        x["score"] = round(x["score"] / mx, 4)
        x.pop("bm25", None)
        x.pop("tfidf", None)
    return top


def source_file_of(conn, doc_id: str) -> str:
    row = conn.execute(
        "SELECT source_file FROM documents WHERE doc_id = ?", (doc_id,)
    ).fetchone()
    return row["source_file"] if row else doc_id
