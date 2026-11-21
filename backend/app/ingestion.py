"""入库 + 注入隔离 + 滑动窗口切块 + FTS5/向量双索引（ARCHITECTURE §2 / §3）。

P1 进化升级：
1. SHA-256 内容寻址幂等：同名文件未改动直接返回既有记录；内容变更时原子重建该文档的
   chunks / chunks_fts / injection_excerpts，支持知识库文档修订热更新；
2. 滑动窗口长段切分（Parent-Child）：超长段落按句界 + Overlap 切分并记录 parent_para_id，
   防止大段撑爆上下文窗口；短段落保持原样；
3. 入库同步写入 SQLite FTS5 (`chunks_fts`) 与可选本地稠密向量 (`chunks.embedding`)，
   同时保留 bm25_vec / tfidf_vec 兼容存量测试。
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import settings
from .db import fts_tokenize, get_conn
from .embeddings import embed_texts, pack_vector
from .injection import RISK_WARNING_MESSAGE, strip_injection
from .parsers import Para, Section, parse_file


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
    risk_warning: str | None = None
    content_sha256: str | None = None
    updated: bool = False


_TOKEN_RE = re.compile(r"[一-龥]+|[a-zA-Z0-9]+")
_SPLIT_SENT_RE = re.compile(r"(?<=[。；;!！？?\n])|(?<=\.)(?=\s|$)")


def tokenize(text: str) -> list[str]:
    """中文 CJK bigram + 英文/数字整词分词（与 FTS5 索引同源）。"""
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
            tokens.append(s)
    return tokens


def _meaningful(text: str) -> bool:
    return any(("一" <= ch <= "龥") or ch.isalnum() for ch in text)


def _heading_path(title: str, section_heading: str) -> str:
    if section_heading:
        return f"{title} > {section_heading}"
    return title


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def split_long_text(
    text: str, *, max_chars: int = 500, overlap_chars: int = 80
) -> list[str]:
    """超长段落按句界切分并保留重叠上下文，短段落原样返回。"""
    t = (text or "").strip()
    if not t or max_chars <= 0 or len(t) <= max_chars:
        return [t] if t else []

    overlap = min(max(overlap_chars, 0), max_chars // 2)
    sents = [s for s in _SPLIT_SENT_RE.split(t) if s]
    chunks: list[str] = []
    buf = ""
    for sent in sents:
        if len(sent) > max_chars:
            if buf.strip():
                chunks.append(buf.strip())
                buf = ""
            step = max(1, max_chars - overlap)
            for start in range(0, len(sent), step):
                piece = sent[start : start + max_chars].strip()
                if piece:
                    chunks.append(piece)
                if start + max_chars >= len(sent):
                    break
            continue
        if len(buf) + len(sent) <= max_chars:
            buf += sent
        else:
            if buf.strip():
                chunks.append(buf.strip())
            tail = buf[-overlap:] if overlap > 0 else ""
            buf = (tail + sent).lstrip()
    if buf.strip():
        chunks.append(buf.strip())
    return chunks


def bm25_weights(
    term_freqs: dict[str, int],
    doc_len: int,
    avg_dl: float,
    k1: float = 1.5,
    b: float = 0.75,
) -> dict[str, float]:
    out: dict[str, float] = {}
    for term, tf in term_freqs.items():
        denom = tf + k1 * (1 - b + b * (doc_len / avg_dl if avg_dl > 0 else 1.0))
        out[term] = round(tf * (k1 + 1) / denom, 6)
    return out


def tfidf_weights(term_freqs: dict[str, int], idf: dict[str, float]) -> dict[str, float]:
    return {t: round(tf * idf.get(t, 0.0), 6) for t, tf in term_freqs.items()}


def _next_doc_id(conn) -> str:
    rows = conn.execute("SELECT doc_id FROM documents").fetchall()
    max_num = 0
    for r in rows:
        m = re.match(r"^doc(\d+)$", r["doc_id"] or "")
        if m:
            max_num = max(max_num, int(m.group(1)))
    return f"doc{max_num + 1:02d}"


def ingest_file(
    source_path,
    *,
    title: str | None = None,
    source_file: str | None = None,
    db_path: str | None = None,
) -> IngestResult:
    """解析单个文件并入库（SHA-256 幂等/热更新 + 注入隔离 + 滑动切块 + FTS5/向量双索引）。"""
    p = Path(str(source_path))
    fmt = p.suffix.lower().lstrip(".")
    if fmt == "txt":
        fmt = "md"
    if fmt not in ("md", "docx", "doc"):
        raise ValueError(f"不支持的格式：{p.suffix}")
    parse_method = {
        "md": "读取原 Markdown 文本",
        "docx": "OOXML(word/document.xml) 解析",
        "doc": "UTF-16 文本流提取（失败回退 LibreOffice 转 docx）",
    }[fmt]

    content_hash = _file_sha256(p)
    sections = parse_file(p)
    if not sections:
        raise ValueError(f"解析结果为空：{p}")

    if title is None:
        title = p.stem
    if source_file is None:
        source_file = p.name

    blocks: list[tuple[Section, Para]] = []
    for sec in sections:
        for para in sec.blocks:
            blocks.append((sec, para))
    if not blocks:
        raise ValueError(f"解析结果无内容块：{p}")

    max_chars = int(getattr(settings, "chunk_max_chars", 500))
    overlap_chars = int(getattr(settings, "chunk_overlap_chars", 80))

    # 注入过滤 + 超长段滑动切分（保留父段分组编号以便溯源）
    kept: list[tuple[Section, Para, int]] = []
    isolated: list[dict] = []
    group_no = 0
    for sec, para in blocks:
        clean, removed, hits = strip_injection(para.text)
        if hits:
            isolated.append(
                {
                    "heading_path": _heading_path(title, sec.heading),
                    "block_type": para.type.value,
                    "text": "".join(removed) if removed else para.text,
                    "matched_keywords": hits,
                }
            )
        if clean and _meaningful(clean):
            group_no += 1
            for piece in split_long_text(
                clean, max_chars=max_chars, overlap_chars=overlap_chars
            ):
                if _meaningful(piece):
                    kept.append((sec, Para(type=para.type, text=piece), group_no))

    # 兼容稀疏向量统计
    term_freqs: list[dict[str, int]] = []
    for _, para, _ in kept:
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

    # 可选稠密向量
    vectors = embed_texts([para.text for _, para, _ in kept]) if kept else None

    created_at = _utcnow()
    with get_conn(db_path) as conn:
        existing = conn.execute(
            "SELECT id, doc_id, char_count, injection_flag, risk_warning,"
            " content_sha256, created_at FROM documents WHERE source_file = ?",
            (source_file,),
        ).fetchone()

        updated = False
        if existing:
            # 内容哈希一致（或旧库未记哈希且字符数相同）→ 幂等跳过
            if existing["content_sha256"] == content_hash:
                chunks = conn.execute(
                    "SELECT COUNT(*) AS n FROM chunks WHERE doc_id = ?",
                    (existing["doc_id"],),
                ).fetchone()["n"]
                injs = conn.execute(
                    "SELECT COUNT(*) AS n FROM injection_excerpts WHERE doc_id = ?",
                    (existing["doc_id"],),
                ).fetchone()["n"]
                return IngestResult(
                    doc_id=existing["doc_id"],
                    title=title,
                    source_file=source_file,
                    source_format=fmt,
                    parse_method=parse_method,
                    char_count=existing["char_count"],
                    injection_flag=existing["injection_flag"],
                    chunk_count=chunks,
                    injection_excerpt_count=injs,
                    created_at=existing["created_at"],
                    risk_warning=existing["risk_warning"],
                    content_sha256=existing["content_sha256"],
                    updated=False,
                )
            # 同名文件内容发生变化 → 原地热更新（保留 doc_id，原子替换切块与索引）
            doc_id = existing["doc_id"]
            updated = True
            conn.execute("DELETE FROM chunks_fts WHERE doc_id = ?", (doc_id,))
            conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
            conn.execute("DELETE FROM injection_excerpts WHERE doc_id = ?", (doc_id,))
            char_count = sum(para.chars for _, para, _ in kept)
            risk_warning = RISK_WARNING_MESSAGE if isolated else None
            conn.execute(
                "UPDATE documents SET title=?, source_format=?, parse_method=?,"
                " char_count=?, injection_flag=?, risk_warning=?, content_sha256=?,"
                " created_at=? WHERE doc_id=?",
                (
                    title,
                    fmt,
                    parse_method,
                    char_count,
                    1 if isolated else 0,
                    risk_warning,
                    content_hash,
                    created_at,
                    doc_id,
                ),
            )
        else:
            doc_id = _next_doc_id(conn)
            char_count = sum(para.chars for _, para, _ in kept)
            risk_warning = RISK_WARNING_MESSAGE if isolated else None
            conn.execute(
                "INSERT INTO documents (doc_id, title, source_file, source_format,"
                " parse_method, char_count, injection_flag, risk_warning,"
                " content_sha256, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    doc_id,
                    title,
                    source_file,
                    fmt,
                    parse_method,
                    char_count,
                    1 if isolated else 0,
                    risk_warning,
                    content_hash,
                    created_at,
                ),
            )

        for idx, ((sec, para, gno), tf, dlen) in enumerate(
            zip(kept, term_freqs, doc_lengths), start=1
        ):
            para_id = f"{doc_id}#p{idx:03d}"
            parent_para_id = f"{doc_id}#g{gno:03d}"
            heading = _heading_path(title, sec.heading)
            bm = bm25_weights(tf, dlen, avg_dl)
            tfv = tfidf_weights(tf, idf)
            emb_blob = pack_vector(vectors[idx - 1]) if vectors else None
            conn.execute(
                "INSERT INTO chunks (doc_id, para_id, parent_para_id, heading_path,"
                " block_type, text, chars, bm25_vec, tfidf_vec, embedding)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    doc_id,
                    para_id,
                    parent_para_id,
                    heading,
                    para.type.value,
                    para.text,
                    para.chars,
                    json.dumps(bm, ensure_ascii=False),
                    json.dumps(tfv, ensure_ascii=False),
                    emb_blob,
                ),
            )
            conn.execute(
                "INSERT INTO chunks_fts (para_id, doc_id, tokens) VALUES (?, ?, ?)",
                (para_id, doc_id, fts_tokenize(para.text)),
            )

        for i, ex in enumerate(isolated, start=1):
            conn.execute(
                "INSERT INTO injection_excerpts (doc_id, para_id, heading_path,"
                " block_type, text, matched_keywords, created_at)"
                " VALUES (?,?,?,?,?,?,?)",
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
            risk_warning=risk_warning,
            content_sha256=content_hash,
            updated=updated,
        )


def load_initial_corpus(kb_dir, db_path: str | None = None) -> list[IngestResult]:
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
