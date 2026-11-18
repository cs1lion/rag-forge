"""SQLite 连接与建表。

4 张表（documents / chunks / qa_records / video_tasks）字段定义
与 docs/ARCHITECTURE.md §2 完全一致；任何字段变更须先改架构文档再改这里。
"""
import sqlite3
from pathlib import Path

STORAGE = Path(__file__).resolve().parent.parent / "storage"
DB_PATH = STORAGE / "app.db"

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
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    para_id TEXT NOT NULL,
    heading_path TEXT NOT NULL DEFAULT '',
    block_type TEXT NOT NULL DEFAULT 'text',
    text TEXT NOT NULL,
    chars INTEGER NOT NULL DEFAULT 0,
    bm25_vec TEXT NOT NULL DEFAULT '{}',
    tfidf_vec TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id);

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
    video_path TEXT,
    error TEXT,
    queue_position INTEGER,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);
"""


def get_conn(db_path: str | Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path or DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: str | Path | None = None) -> None:
    STORAGE.mkdir(parents=True, exist_ok=True)
    with get_conn(db_path) as conn:
        conn.executescript(SCHEMA)
