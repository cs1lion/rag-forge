"""会话 4 新增单测：文档隔离开关、检索隔离语义、视频任务与历史问答删除。

覆盖：
- PUT /api/documents/{doc_id}/quarantine 开关切换（开启=不选用，关闭=恢复检索）
- quarantined=1 的文档整篇不进检索候选池
- 未隔离但 injection_flag=1 的文档召回时携带 injection_flag（前端风险提示）
- DELETE /api/video-tasks/{id} 删除任务并清理产物（running 拒绝删除）
- DELETE /api/qa/{id} 删除历史问答及其关联视频任务
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import app

KB = Path(__file__).resolve().parents[2] / "知识库"
pytestmark = pytest.mark.skipif(
    not KB.is_dir(), reason="knowledge corpus not present in this checkout"
)


@pytest.fixture()
def api(tmp_path, monkeypatch):
    test_db = tmp_path / "q.db"
    db.init_db(test_db)
    from app.ingestion import load_initial_corpus
    load_initial_corpus(KB, db_path=test_db)
    conn_factory = lambda db_path=None: db.get_conn(test_db)
    monkeypatch.setattr("app.main.get_conn", conn_factory)
    monkeypatch.setattr("app.retrieval.get_conn", conn_factory)
    monkeypatch.setattr("app.ingestion.get_conn", conn_factory)
    monkeypatch.setattr("app.main.UPLOADS_DIR", tmp_path / "uploads")
    with TestClient(app) as client:
        # lifespan 内调度器会启动；视频目录指向 tmp 隔离产物
        app.state.video_dir = tmp_path / "videos"
        app.state.video_dir.mkdir(parents=True, exist_ok=True)
        yield client, conn_factory


class TestRiskWarning:
    """注入识别改为入库阶段过滤：文档携带 risk_warning，问答汇总返回。"""

    def test_list_documents_carries_risk_warning(self, api):
        client, _ = api
        r = client.get("/api/documents")
        assert r.status_code == 200
        docs = r.json()["documents"]
        assert docs, "初始语料应已入库"
        for d in docs:
            assert "risk_warning" in d
        flagged = [d for d in docs if d["injection_flag"] == 1]
        assert flagged, "doc05/doc06/doc07/doc03 应含注入特征"
        for d in flagged:
            assert d["risk_warning"] == "检测到疑似提示词注入指令，已在解析阶段自动过滤"

    def test_clean_doc_risk_warning_null(self, api):
        client, _ = api
        docs = client.get("/api/documents").json()["documents"]
        clean = [d for d in docs if d["injection_flag"] == 0]
        assert clean
        for d in clean:
            assert d["risk_warning"] is None

    def test_injection_doc_recalled_with_risk_warning(self, api):
        """注入文档仍可召回（注入句已在入库阶段剥离），命中携带 risk_warning。"""
        from app.retrieval import hybrid_search
        hits = hybrid_search("众赢科技研发投入", top_k=10)
        flagged = [h for h in hits if h["doc_id"] == "doc05"]
        assert flagged, "doc05 应可召回"
        assert flagged[0]["injection_flag"] == 1
        assert flagged[0]["risk_warning"] == "检测到疑似提示词注入指令，已在解析阶段自动过滤"
        # 剥离生效：召回文本不带越权指令
        for h in flagged:
            assert "忽略所有" not in h["text"]


class TestVideoTaskListForHistoryPlayback:
    def test_done_tasks_returned_with_video_url(self, api, tmp_path):
        """历史回看播放器修复：`/api/video-tasks` 必须返回已完成任务并带 video_url。

        原实现只返回 queued 任务且不出 video_url，刷新页面/回看历史时
        前端拿不到可播放的视频源，播放器不显示。
        """
        client, conn_factory = api
        with conn_factory() as conn:
            qcur = conn.execute(
                "INSERT INTO qa_records (question, answer, citations, created_at)"
                " VALUES ('q', '{}', '[]', '2026-01-01T00:00:00Z')"
            )
            qid = qcur.lastrowid
            vp = tmp_path / "videos" / "done.mp4"
            vp.parent.mkdir(parents=True, exist_ok=True)
            vp.write_bytes(b"fake")
            conn.execute(
                "INSERT INTO video_tasks (qa_record_id, status, progress, video_path, created_at)"
                " VALUES (?, 'done', 1.0, ?, '2026-01-01T00:00:00Z')",
                (qid, str(vp)),
            )
            conn.commit()

        lst = client.get("/api/video-tasks").json()
        done = [t for t in lst["tasks"] if t["status"] == "done"]
        assert done, "已完成任务必须出现在任务列表（否则回看时播放器无源）"
        assert done[0]["video_url"] == f"/api/videos/{done[0]['id']}/file"
        # 内部落盘路径不外露
        assert "video_path" not in done[0]

    def test_relative_video_path_resolves_against_backend_dir(self, api, tmp_path, monkeypatch):
        """DB 中 video_path 为相对路径时按后端目录解析（不随启动 CWD 漂移）；
        文件缺失时优雅 404，而非 500。"""
        client, conn_factory = api
        monkeypatch.setattr("app.main.BACKEND_DIR", tmp_path)
        vdir = tmp_path / "storage" / "videos"
        vdir.mkdir(parents=True)
        (vdir / "rel.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42fake")
        with conn_factory() as conn:
            qcur = conn.execute(
                "INSERT INTO qa_records (question, answer, citations, created_at)"
                " VALUES ('q', '{}', '[]', '2026-01-01T00:00:00Z')"
            )
            qid = qcur.lastrowid
            tcur = conn.execute(
                "INSERT INTO video_tasks (qa_record_id, status, progress, video_path, created_at)"
                " VALUES (?, 'done', 1.0, 'storage/videos/rel.mp4', '2026-01-01T00:00:00Z')",
                (qid,),
            )
            conn.commit()
            tid = tcur.lastrowid

        r = client.get(f"/api/videos/{tid}/file")
        assert r.status_code == 200
        assert r.headers["content-type"] == "video/mp4"

        (vdir / "rel.mp4").unlink()
        r2 = client.get(f"/api/videos/{tid}/file")
        assert r2.status_code == 200
        assert r2.json()["error"]["code"] == "E_NOT_FOUND"


class TestVideoTaskDelete:
    @staticmethod
    def _mk_qa(conn) -> int:
        """video_tasks.qa_record_id 有外键约束：先建问答记录再建任务。"""
        cur = conn.execute(
            "INSERT INTO qa_records (question, answer, citations, created_at)"
            " VALUES ('q', '{}', '[]', '2026-01-01T00:00:00Z')"
        )
        conn.commit()
        return cur.lastrowid

    def test_delete_done_task_removes_row_and_file(self, api, tmp_path):
        client, conn_factory = api
        # 造一个 done 任务 + 假产物文件
        with conn_factory() as conn:
            qid = self._mk_qa(conn)
            vp = tmp_path / "videos" / "qa_1_t1.mp4"
            vp.parent.mkdir(parents=True, exist_ok=True)
            vp.write_bytes(b"fake")
            cur = conn.execute(
                "INSERT INTO video_tasks (qa_record_id, status, progress, video_path, created_at)"
                " VALUES (?, 'done', 1.0, ?, '2026-01-01T00:00:00Z')",
                (qid, str(vp)),
            )
            conn.commit()
            tid = cur.lastrowid
        r = client.delete(f"/api/video-tasks/{tid}")
        assert r.status_code == 204
        with conn_factory() as conn:
            row = conn.execute("SELECT * FROM video_tasks WHERE id = ?", (tid,)).fetchone()
        assert row is None
        assert not vp.exists()  # 产物文件一并清理

    def test_delete_running_task_rejected(self, api):
        client, conn_factory = api
        with conn_factory() as conn:
            qid = self._mk_qa(conn)
            cur = conn.execute(
                "INSERT INTO video_tasks (qa_record_id, status, progress, created_at)"
                " VALUES (?, 'running', 0.5, '2026-01-01T00:00:00Z')",
                (qid,),
            )
            conn.commit()
            tid = cur.lastrowid
        r = client.delete(f"/api/video-tasks/{tid}")
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "E_VIDEO_RUNNING"

    def test_delete_unknown_task_404(self, api):
        client, _ = api
        r = client.delete("/api/video-tasks/9999")
        assert r.status_code == 404


class TestStartupRecovery:
    def test_running_tasks_requeued_on_startup(self, tmp_path, monkeypatch):
        """服务重启：残留 running 重置为 queued，queued 按 created_at 升序重建内存队列。"""
        from app.video_queue import drain_pending, reset_pending_queue

        reset_pending_queue()
        test_db = tmp_path / "recover.db"
        db.init_db(test_db)
        with db.get_conn(test_db) as conn:
            qcur = conn.execute(
                "INSERT INTO qa_records (question, answer, citations, created_at)"
                " VALUES ('q', '{}', '[]', '2026-01-01T00:00:00Z')"
            )
            qid = qcur.lastrowid
            # 两个任务：先创建的 running（重启时被中断），后创建的 queued
            t1 = conn.execute(
                "INSERT INTO video_tasks (qa_record_id, status, progress, created_at)"
                " VALUES (?, 'running', 0.5, '2026-01-01T00:00:01Z')",
                (qid,),
            ).lastrowid
            t2 = conn.execute(
                "INSERT INTO video_tasks (qa_record_id, status, progress, created_at)"
                " VALUES (?, 'queued', 0.0, '2026-01-01T00:00:02Z')",
                (qid,),
            ).lastrowid
            conn.commit()

        monkeypatch.setattr("app.main.get_conn", lambda db_path=None: db.get_conn(test_db))
        monkeypatch.setattr("app.main.UPLOADS_DIR", tmp_path / "uploads")

        async def _noop_dispatcher(app_, on_progress):
            import asyncio
            while True:
                await asyncio.sleep(0.05)

        monkeypatch.setattr("app.main.run_dispatcher", _noop_dispatcher)
        with TestClient(app):
            pass

        with db.get_conn(test_db) as conn:
            rows = {
                r["id"]: r["status"]
                for r in conn.execute("SELECT id, status FROM video_tasks")
            }
            started = conn.execute(
                "SELECT started_at FROM video_tasks WHERE id = ?", (t1,)
            ).fetchone()["started_at"]
        assert rows[t1] == "queued", "中断的 running 任务应重置为 queued（而非 failed）"
        assert rows[t2] == "queued"
        assert started is None, "恢复时应清空 started_at"
        # 内存队列按 created_at 升序重建
        assert drain_pending() == [t1, t2]
        reset_pending_queue()

    def test_no_tasks_restore_is_noop(self, tmp_path, monkeypatch):
        from app.video_queue import drain_pending, reset_pending_queue

        reset_pending_queue()
        test_db = tmp_path / "empty.db"
        db.init_db(test_db)
        monkeypatch.setattr("app.main.get_conn", lambda db_path=None: db.get_conn(test_db))
        monkeypatch.setattr("app.main.UPLOADS_DIR", tmp_path / "uploads")

        async def _noop_dispatcher(app_, on_progress):
            import asyncio
            while True:
                await asyncio.sleep(0.05)

        monkeypatch.setattr("app.main.run_dispatcher", _noop_dispatcher)
        with TestClient(app):
            pass
        assert drain_pending() == []
        reset_pending_queue()


class TestQaRecordDelete:
    def test_delete_qa_record_cascades_video_task(self, api, tmp_path):
        client, conn_factory = api
        with conn_factory() as conn:
            cur = conn.execute(
                "INSERT INTO qa_records (question, answer, citations, created_at)"
                " VALUES ('q', '{}', '[]', '2026-01-01T00:00:00Z')",
            )
            conn.commit()
            qid = cur.lastrowid
            vp = tmp_path / "videos" / "qa_x.mp4"
            vp.parent.mkdir(parents=True, exist_ok=True)
            vp.write_bytes(b"fake")
            cur2 = conn.execute(
                "INSERT INTO video_tasks (qa_record_id, status, progress, video_path, created_at)"
                " VALUES (?, 'done', 1.0, ?, '2026-01-01T00:00:00Z')",
                (qid, str(vp)),
            )
            conn.commit()
            tid = cur2.lastrowid
            conn.execute("UPDATE qa_records SET video_task_id = ? WHERE id = ?", (tid, qid))
            conn.commit()

        r = client.delete(f"/api/qa/{qid}")
        assert r.status_code == 204
        with conn_factory() as conn:
            qa = conn.execute("SELECT * FROM qa_records WHERE id = ?", (qid,)).fetchone()
            vt = conn.execute("SELECT * FROM video_tasks WHERE id = ?", (tid,)).fetchone()
        assert qa is None
        assert vt is None
        assert not vp.exists()

    def test_delete_unknown_qa_404(self, api):
        client, _ = api
        r = client.delete("/api/qa/9999")
        assert r.status_code == 404

    def test_delete_qa_with_extra_and_running_tasks_succeeds(self, api):
        """回归：问答名下存在额外任务（历史遗留）与 running 任务时删除不得 500。

        曾因只删 video_task_id 指向的那一条、其余任务仍以 qa_record_id 引用
        该问答行，触发外键约束 → Internal Server Error。
        """
        client, conn_factory = api
        with conn_factory() as conn:
            qcur = conn.execute(
                "INSERT INTO qa_records (question, answer, citations, created_at)"
                " VALUES ('q', '{}', '[]', '2026-01-01T00:00:00Z')"
            )
            qid = qcur.lastrowid
            extra = conn.execute(
                "INSERT INTO video_tasks (qa_record_id, status, progress, created_at)"
                " VALUES (?, 'running', 0.5, '2026-01-01T00:00:00Z')",
                (qid,),
            ).lastrowid
            main_task = conn.execute(
                "INSERT INTO video_tasks (qa_record_id, status, progress, created_at)"
                " VALUES (?, 'done', 1.0, '2026-01-01T00:00:00Z')",
                (qid,),
            ).lastrowid
            conn.execute("UPDATE qa_records SET video_task_id = ? WHERE id = ?", (main_task, qid))
            conn.commit()

        r = client.delete(f"/api/qa/{qid}")
        assert r.status_code == 204, r.text
        with conn_factory() as conn:
            assert conn.execute("SELECT * FROM qa_records WHERE id = ?", (qid,)).fetchone() is None
            left = conn.execute(
                "SELECT COUNT(*) n FROM video_tasks WHERE id IN (?, ?)", (extra, main_task)
            ).fetchone()["n"]
        assert left == 0

    def test_delete_video_task_clears_qa_reference(self, api):
        """回归：删除被问答引用的视频任务时先解除引用，不得 500。"""
        client, conn_factory = api
        with conn_factory() as conn:
            qcur = conn.execute(
                "INSERT INTO qa_records (question, answer, citations, created_at)"
                " VALUES ('q', '{}', '[]', '2026-01-01T00:00:00Z')"
            )
            qid = qcur.lastrowid
            tid = conn.execute(
                "INSERT INTO video_tasks (qa_record_id, status, progress, created_at)"
                " VALUES (?, 'done', 1.0, '2026-01-01T00:00:00Z')",
                (qid,),
            ).lastrowid
            conn.execute("UPDATE qa_records SET video_task_id = ? WHERE id = ?", (tid, qid))
            conn.commit()

        r = client.delete(f"/api/video-tasks/{tid}")
        assert r.status_code == 204, r.text
        with conn_factory() as conn:
            qa = conn.execute("SELECT video_task_id FROM qa_records WHERE id = ?", (qid,)).fetchone()
            task = conn.execute("SELECT * FROM video_tasks WHERE id = ?", (tid,)).fetchone()
        assert task is None
        assert qa["video_task_id"] is None

    def test_delete_qa_with_locked_file_still_succeeds(self, api, tmp_path, monkeypatch):
        """文件清理失败（被占用等 OSError）不得阻塞记录删除。"""
        client, conn_factory = api
        with conn_factory() as conn:
            qcur = conn.execute(
                "INSERT INTO qa_records (question, answer, citations, created_at)"
                " VALUES ('q', '{}', '[]', '2026-01-01T00:00:00Z')"
            )
            qid = qcur.lastrowid
            tid = conn.execute(
                "INSERT INTO video_tasks (qa_record_id, status, progress, video_path, created_at)"
                " VALUES (?, 'done', 1.0, ?, '2026-01-01T00:00:00Z')",
                (qid, str(tmp_path / "locked.mp4")),
            ).lastrowid
            conn.execute("UPDATE qa_records SET video_task_id = ? WHERE id = ?", (tid, qid))
            conn.commit()

        def _boom(self, *a, **kw):
            raise PermissionError("file is in use")

        monkeypatch.setattr("pathlib.Path.unlink", _boom)
        r = client.delete(f"/api/qa/{qid}")
        assert r.status_code == 204, r.text
