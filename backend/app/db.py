"""SQLite 连接、建表、FTS5 倒排索引与幂等迁移。

P0 + P1 升级：
- 开启 PRAGMA journal_mode=WAL、synchronous=NORMAL、busy_timeout；
- 新增 chunks_fts (SQLite FTS5) 倒排虚表，消除全表扫描与双次 JSON 反序列化；
- 幂等补齐 documents.content_sha256、chunks.parent_para_id、chunks.embedding、
  video_tasks.attempt_count、video_tasks.cancel_requested 列；
- 自动为旧库历史 chunks 回填 chunks_fts 索引。
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from .config import settings

STORAGE = Path(__file__).resolve().parent.parent / "storage"
DB_PATH = STORAGE / "app.db"

_TOKEN_RE = re.compile(r"[一-龥]+|[a-zA-Z0-9]+")


def fts_tokenize(text: str) -> str:
    """将文本转为适合 SQLite FTS5 unicode61 索引的空格分隔 CJK bigram + 英文词元串。"""
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
    return " ".join(tokens)


SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    source_file TEXT NOT NULL,
    source_format TEXT NOT NULL,
    parse_method TEXT NOT NULL,
    char_count INTEGER NOT NULL DEFAULT 0,
    injection_flag INTEGER NOT NULL DEFAULT 0,
    risk_warning TEXT,
    content_sha256 TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    para_id TEXT NOT NULL,
    parent_para_id TEXT NOT NULL DEFAULT '',
    heading_path TEXT NOT NULL DEFAULT '',
    block_type TEXT NOT NULL DEFAULT 'text',
    text TEXT NOT NULL,
    chars INTEGER NOT NULL DEFAULT 0,
    bm25_vec TEXT NOT NULL DEFAULT '{}',
    tfidf_vec TEXT NOT NULL DEFAULT '{}',
    embedding BLOB
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id);
CREATE INDEX IF NOT EXISTS idx_chunks_para ON chunks(para_id);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    para_id UNINDEXED,
    doc_id UNINDEXED,
    tokens,
    tokenize = 'unicode61'
);

CREATE TABLE IF NOT EXISTS injection_excerpts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    para_id TEXT NOT NULL,
    heading_path TEXT NOT NULL DEFAULT '',
    block_type TEXT NOT NULL DEFAULT 'text',
    text TEXT NOT NULL,
    matched_keywords TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_inj_doc ON injection_excerpts(doc_id);

CREATE TABLE IF NOT EXISTS qa_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    citations TEXT NOT NULL DEFAULT '[]',
    video_task_id INTEGER REFERENCES video_tasks(id),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS video_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    qa_record_id INTEGER REFERENCES qa_records(id),
    status TEXT NOT NULL DEFAULT 'queued',
    progress REAL NOT NULL DEFAULT 0.0,
    stage TEXT NOT NULL DEFAULT '',
    stage_text TEXT,
    video_path TEXT,
    error TEXT,
    queue_position INTEGER,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);
"""


def try_load_sqlite_vec(conn: sqlite3.Connection) -> bool:
    """若环境安装了 sqlite_vec 扩展则按需加载，否则安静回退到纯 Python 向量相似度。"""
    try:
        import sqlite_vec  # type: ignore

        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        return True
    except Exception:
        return False


def get_conn(db_path: str | Path | None = None) -> sqlite3.Connection:
    target = str(db_path or DB_PATH)
    busy_ms = max(1000, int(getattr(settings, "db_busy_timeout_ms", 5000)))
    conn = sqlite3.connect(target, timeout=busy_ms / 1000.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {busy_ms}")
    if target != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
    return conn


MIGRATIONS: list[tuple[str, str]] = [
    ("documents.risk_warning", "ALTER TABLE documents ADD COLUMN risk_warning TEXT"),
    ("documents.content_sha256", "ALTER TABLE documents ADD COLUMN content_sha256 TEXT"),
    (
        "chunks.parent_para_id",
        "ALTER TABLE chunks ADD COLUMN parent_para_id TEXT NOT NULL DEFAULT ''",
    ),
    ("chunks.embedding", "ALTER TABLE chunks ADD COLUMN embedding BLOB"),
    ("video_tasks.stage_text", "ALTER TABLE video_tasks ADD COLUMN stage_text TEXT"),
    (
        "video_tasks.attempt_count",
        "ALTER TABLE video_tasks ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0",
    ),
    (
        "video_tasks.cancel_requested",
        "ALTER TABLE video_tasks ADD COLUMN cancel_requested INTEGER NOT NULL DEFAULT 0",
    ),
]


def _migrate(conn: sqlite3.Connection) -> None:
    """幂等迁移：为既有库补齐新列（列已存在则跳过）。"""
    for name, ddl in MIGRATIONS:
        table, col = name.split(".", 1)
        cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        if col not in cols:
            conn.execute(ddl)


def _backfill_fts5(conn: sqlite3.Connection) -> None:
    """为旧库中尚未写入 chunks_fts 的历史段落回填 FTS5 倒排索引。"""
    total_chunks = conn.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()["n"]
    if total_chunks == 0:
        return
    total_fts = conn.execute("SELECT COUNT(*) AS n FROM chunks_fts").fetchone()["n"]
    if total_fts >= total_chunks:
        return
    existing = {r["para_id"] for r in conn.execute("SELECT para_id FROM chunks_fts")}
    rows = conn.execute("SELECT para_id, doc_id, text FROM chunks").fetchall()
    missing = [
        (r["para_id"], r["doc_id"], fts_tokenize(r["text"]))
        for r in rows
        if r["para_id"] not in existing
    ]
    if missing:
        conn.executemany(
            "INSERT INTO chunks_fts (para_id, doc_id, tokens) VALUES (?, ?, ?)",
            missing,
        )


def init_db(db_path: str | Path | None = None) -> None:
    if db_path is None:
        STORAGE.mkdir(parents=True, exist_ok=True)
    elif str(db_path) != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with get_conn(db_path) as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)
        _backfill_fts5(conn)
        conn.commit()
