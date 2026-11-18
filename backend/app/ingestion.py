"""入库 + 注入隔离 + 切块（ARCHITECTURE §2 / §3）。

职责：
- 文档解析（三级容错）→ Section/Para；
- 注入隔离：命中可疑特征的段落**不进 chunks**，仅在
  `documents.injection_flag` 记 1，原文隔离存档（可溯源但不参与召回）；
- 四维元数据切块：doc_id / source_file / heading_path / para_id；
- 稀疏向量本地计算：BM25 词项权重 + TF-IDF（零外部 Embedding）。
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from .db import get_conn
from .injection import scan_injection
from .parsers import BlockType, Para, Section, parse_file


@dataclass
class IngestResult:
    doc_id: str
    title: str
    source_file: str
    source_format: str
    parse_method: str
    char_count: int
    injection_flag: int
    chunk_count: int
    injection_excerpt_count: int
    created_at: str


# ---------------------------------------------------------------- 工具

_TOKEN_RE = re.compile(r"[一-鿿]+|[a-zA-Z0-9]+")


def tokenize(text: str) -> list[str]:
    """中文 CJK bigram + 英文/数字整词分词（本地稀疏向量用）。

    连续 CJK 段拆为 bigram（相邻两字），短段（<=2 字）保留原样；
    英文/数字按连续 token 整词保留。bigram 使查询与文档的词项可交叉匹配。
    """
    tokens: list[str] = []
    for m in _TOKEN_RE.finditer(text):
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


def _heading_path(title: str, section_heading: str) -> str:
    if section_heading:
        return f"{title} > {section_heading}"
    return title


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------- 稀疏向量

def bm25_weights(term_freqs: dict[str, int], doc_len: int, avg_dl: float, k1: float = 1.5, b: float = 0.75) -> dict[str, float]:
    """单文档 BM25 词项权重（语料级 IDF 由调用方并入 tfidf_vec）。

    BM25 = idf * tf*(k1+1) / (tf + k1*(1 - b + b*dl/avgdl))；
    此处 idf 取 1（语料级修正由检索端混合时处理），仅做文档内归一。
    """
    out: dict[str, float] = {}
    for term, tf in term_freqs.items():
        denom = tf + k1 * (1 - b + b * (doc_len / avg_dl if avg_dl > 0 else 1.0))
        out[term] = round(tf * (k1 + 1) / denom, 6)
    return out


def tfidf_weights(term_freqs: dict[str, int], idf: dict[str, float]) -> dict[str, float]:
    """TF-IDF 稀疏向量：tf * idf（idf 由语料级统计给出）。"""
    return {t: round(tf * idf.get(t, 0.0), 6) for t, tf in term_freqs.items()}


# ---------------------------------------------------------------- 入库

def _next_doc_id(conn) -> str:
    row = conn.execute("SELECT COUNT(*) AS n FROM documents").fetchone()
    return f"doc{row['n'] + 1:02d}"


def ingest_file(
    source_path,
    *,
    title: str | None = None,
    source_file: str | None = None,
    db_path: str | None = None,
) -> IngestResult:
    """解析单个文件并入库（注入隔离 + 四维切块 + 稀疏向量）。

    幂等：同一 `source_file` 已存在时直接返回既有记录（不重复入库）。
    """
    from pathlib import Path

    p = Path(str(source_path))
    fmt = p.suffix.lower().lstrip(".")
    if fmt == "txt":
        fmt = "md"
    if fmt not in ("md", "docx", "doc"):
        raise ValueError(f"不支持的格式: {p.suffix}")
    parse_method = {
        "md": "读取原 Markdown 文本",
        "docx": "OOXML(word/document.xml) 解析",
        "doc": "UTF-16 文本流提取（失败回退 LibreOffice 转 docx）",
    }[fmt]

    sections = parse_file(p)
    if not sections:
        raise ValueError(f"解析结果为空: {p}")

    if title is None:
        title = p.stem
    if source_file is None:
        source_file = p.name

    blocks: list[tuple[Section, Para]] = []
    for sec in sections:
        for para in sec.blocks:
            blocks.append((sec, para))
    if not blocks:
        raise ValueError(f"解析结果无内容块: {p}")

    # 注入隔离扫描（入库即执行）
    kept: list[tuple[Section, Para]] = []
    isolated: list[dict] = []
    for sec, para in blocks:
        hits = scan_injection(para.text)
        if hits:
            isolated.append(
                {
                    "heading_path": _heading_path(title, sec.heading),
                    "block_type": para.type.value,
                    "text": para.text,
                    "matched_keywords": hits,
                }
            )
        else:
            kept.append((sec, para))

    # 稀疏向量：语料级统计（仅针对保留块）
    term_freqs: list[dict[str, int]] = []
    for sec, para in kept:
        tf: dict[str, int] = {}
        for tok in tokenize(para.text):
            tf[tok] = tf.get(tok, 0) + 1
        term_freqs.append(tf)
    doc_lengths = [sum(tf.values()) for tf in term_freqs]
    avg_dl = sum(doc_lengths) / len(doc_lengths) if doc_lengths else 1.0
    df: dict[str, int] = {}
    for tf in term_freqs:
        for t in tf:
            df[t] = df.get(t, 0) + 1
    n_docs = max(len(term_freqs), 1)
    idf = {t: round(math.log(1 + n_docs / (c + 1)) + 1, 6) for t, c in df.items()}

    created_at = _utcnow()
    with get_conn(db_path) as conn:
        cur = conn.execute(
            "SELECT id FROM documents WHERE source_file = ?",
            (source_file,),
        )
        existing = cur.fetchone()
        if existing:
            row = conn.execute(
                "SELECT doc_id, char_count, injection_flag, created_at FROM documents WHERE id = ?",
                (existing["id"],),
            ).fetchone()
            chunks = conn.execute(
                "SELECT COUNT(*) AS n FROM chunks WHERE doc_id = ?", (row["doc_id"],)
            ).fetchone()["n"]
            injs = conn.execute(
                "SELECT COUNT(*) AS n FROM injection_excerpts WHERE doc_id = ?",
                (row["doc_id"],),
            ).fetchone()["n"]
            return IngestResult(
                doc_id=row["doc_id"],
                title=title,
                source_file=source_file,
                source_format=fmt,
                parse_method=parse_method,
                char_count=row["char_count"],
                injection_flag=row["injection_flag"],
                chunk_count=chunks,
                injection_excerpt_count=injs,
                created_at=row["created_at"],
            )

        doc_id = _next_doc_id(conn)
        char_count = sum(para.chars for _, para in kept)
        conn.execute(
            "INSERT INTO documents (doc_id, title, source_file, source_format, parse_method,"
            " char_count, injection_flag, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (
                doc_id,
                title,
                source_file,
                fmt,
                parse_method,
                char_count,
                1 if isolated else 0,
                created_at,
            ),
        )
        para_no = 0
        for (sec, para), tf, dlen in zip(kept, term_freqs, doc_lengths):
            para_no += 1
            para_id = f"{doc_id}#p{para_no:03d}"
            heading = _heading_path(title, sec.heading)
            bm = bm25_weights(tf, dlen, avg_dl)
            tfv = tfidf_weights(tf, idf)
            conn.execute(
                "INSERT INTO chunks (doc_id, para_id, heading_path, block_type, text, chars,"
                " bm25_vec, tfidf_vec) VALUES (?,?,?,?,?,?,?,?)",
                (
                    doc_id,
                    para_id,
                    heading,
                    para.type.value,
                    para.text,
                    para.chars,
                    json.dumps(bm, ensure_ascii=False),
                    json.dumps(tfv, ensure_ascii=False),
                ),
            )
        for i, ex in enumerate(isolated, start=1):
            conn.execute(
                "INSERT INTO injection_excerpts (doc_id, para_id, heading_path, block_type,"
                " text, matched_keywords, created_at) VALUES (?,?,?,?,?,?,?)",
                (
                    doc_id,
                    f"{doc_id}#i{i:03d}",
                    ex["heading_path"],
                    ex["block_type"],
                    ex["text"],
                    json.dumps(ex["matched_keywords"], ensure_ascii=False),
                    created_at,
                ),
            )
    return IngestResult(
        doc_id=doc_id,
        title=title,
        source_file=source_file,
        source_format=fmt,
        parse_method=parse_method,
        char_count=char_count,
        injection_flag=1 if isolated else 0,
        chunk_count=len(kept),
        injection_excerpt_count=len(isolated),
        created_at=created_at,
    )


def load_initial_corpus(kb_dir, db_path: str | None = None) -> list[IngestResult]:
    """启动时扫描知识库目录，全部初始文档入库（仅当知识库为空）。

    返回本次入库结果列表；目录为空或已全部入库时返回空列表。
    """
    from pathlib import Path

    kdir = Path(str(kb_dir))
    if not kdir.is_dir():
        return []
    with get_conn(db_path) as conn:
        n = conn.execute("SELECT COUNT(*) AS n FROM documents").fetchone()["n"]
    if n > 0:
        return []
    results = []
    for p in sorted(kdir.iterdir()):
        if not p.is_file() or p.name.startswith("._") or p.name == ".DS_Store":
            continue
        if p.suffix.lower() not in (".md", ".txt", ".docx", ".doc"):
            continue
        results.append(ingest_file(p, db_path=db_path))
    return results
