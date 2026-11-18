"""会话 1 骨架冒烟测试：验证 app 可创建、/health 可用、4 张表建表正确。

业务逻辑（解析 / 切块 / 检索 / 溯源 / 问答编排 / 队列调度）的覆盖率门禁
≥ 85% 在后续会话随实现开启（见 backend/pytest.ini 注释与 CLAUDE.md §三）。
"""
import sqlite3

from fastapi.testclient import TestClient

from app import db
from app.main import app


def test_health():
    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["version"] == "0.1.0"


def test_init_db_creates_four_tables(tmp_path):
    test_db = tmp_path / "test_app.db"
    db.init_db(test_db)
    conn = sqlite3.connect(str(test_db))
    try:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        conn.close()
    assert {"documents", "chunks", "qa_records", "video_tasks"} <= tables
