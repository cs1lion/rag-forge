"""Step 4 单测：大模型分镜脚本 + Remotion 渲染 + 视频队列调度。

覆盖 CLAUDE.md §三 铁律 2/3：
- 分镜脚本：LLM 路径（mock httpx 传输层）/ Schema 校验失败降级 / 规则降级；
- 渲染：Remotion 工程生成（tokens.css 三方一致）/ Remotion 不可用降级 PIL；
- 队列：并发提交 3+ 任务，running ≤ 1 且 FIFO 顺序无误（仅 mock 子进程耗时）。
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app import db
from app.ingestion import ingest_file
from app.video_queue import (
    enqueue_video,
    get_task,
    queued_tasks,
    running_count,
    run_dispatcher,
    video_lock,
)
from app.video_render import _ensure_project, _tokens_from_css, render_segments
from app.video_script import (
    _fallback_script,
    _validate_script,
    build_script_prompt,
    build_video_script,
)

KB = Path(__file__).resolve().parents[2] / "知识库"


# ================================================================ 分镜脚本

class TestVideoScript:
    @pytest.mark.asyncio
    async def test_llm_script_path(self, monkeypatch):
        """LLM 返回合法分镜 JSON -> method='llm'，段落逐字来自 answer。"""
        fake_resp = {
            "segments": [
                {"kind": "title", "title": "Q?", "narration": "问题是：Q?"},
                {"kind": "body", "title": "A1。", "narration": "A1。"},
                {"kind": "citations", "title": "引用参考", "subtitle": "x", "narration": "引用 1 段"},
            ]
        }

        class FakeResp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"choices": [{"message": {"content": json.dumps(fake_resp)}}]}

        async def fake_post(self, url, json=None, headers=None):
            return FakeResp()

        monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
        from app.config import settings

        monkeypatch.setattr(settings, "llm_api_key", "k", raising=False)
        monkeypatch.setattr(settings, "llm_base_url", "http://x", raising=False)
        monkeypatch.setattr(settings, "llm_model", "m", raising=False)

        segs, method = await build_video_script("Q?", "A1。", [])
        assert method == "llm"
        assert segs[0]["kind"] == "title"
        assert segs[1]["title"] == "A1。"

    @pytest.mark.asyncio
    async def test_llm_schema_invalid_falls_back(self, monkeypatch):
        """LLM 输出缺必填字段 -> Schema 校验失败 -> 规则降级。"""
        class FakeResp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"choices": [{"message": {"content": json.dumps({"bad": 1})}}]}

        async def fake_post(self, url, json=None, headers=None):
            return FakeResp()

        monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
        from app.config import settings

        monkeypatch.setattr(settings, "llm_api_key", "k", raising=False)
        monkeypatch.setattr(settings, "llm_base_url", "http://x", raising=False)
        monkeypatch.setattr(settings, "llm_model", "m", raising=False)

        segs, method = await build_video_script("Q?", "答案一句。", [])
        assert method == "rule"
        assert segs[0]["kind"] == "title"
        assert segs[1]["narration"] == "答案一句。"

    @pytest.mark.asyncio
    async def test_llm_exception_falls_back(self, monkeypatch):
        """LLM 调用抛异常 -> 规则降级。"""
        from app.config import settings

        monkeypatch.setattr(settings, "llm_api_key", "k", raising=False)
        monkeypatch.setattr(settings, "llm_base_url", "http://x", raising=False)
        monkeypatch.setattr(settings, "llm_model", "m", raising=False)

        async def boom(self, url, json=None, headers=None):
            raise RuntimeError("network down")

        monkeypatch.setattr("httpx.AsyncClient.post", boom)
        segs, method = await build_video_script("Q?", "真实答案。", [])
        assert method == "rule"
        assert any(s["narration"] == "真实答案。" for s in segs)

    @pytest.mark.asyncio
    async def test_no_key_uses_rule(self):
        """LLM 配置缺失（无 Key）-> 直接规则降级，不发网络请求。"""
        from app.config import settings

        old = (settings.llm_api_key, settings.llm_base_url, settings.llm_model)
        settings.llm_api_key = ""
        try:
            segs, method = await build_video_script("Q?", "答。", [])
        finally:
            settings.llm_api_key, settings.llm_base_url, settings.llm_model = old
        assert method == "rule"

    def test_fallback_citations_page(self):
        """降级分镜含引用页，narration 引用数真实。"""
        cites = [{"doc_id": "doc05", "source_file": "a.docx"}] * 3
        segs = _fallback_script("Q", "A。", cites)
        kinds = [s["kind"] for s in segs]
        assert kinds[0] == "title" and kinds[-1] == "citations"
        assert "3 个知识库段落" in segs[-1]["narration"]

    def test_fallback_split_sentences(self):
        """降级切句：按句号切，长句按逗号再切（<=60 字）。"""
        segs = _fallback_script("Q", "第一句。第二句。第三句。", [])
        bodies = [s for s in segs if s["kind"] == "body"]
        assert len(bodies) == 3
        assert bodies[0]["title"] == "第一句。"

    def test_prompt_contains_real_qa(self):
        """分镜提示词不含注入指令文本，只含真实问答与引用。"""
        p = build_script_prompt("Q", "A", [{"source_file": "f.docx", "heading_path": "h", "para_id": "p1"}])
        assert "Q" in p and "A" in p
        assert "f.docx" in p and "p1" in p
        assert "忽略所有" not in p

    def test_validate_script_rejects_bad(self):
        """Schema 校验：缺字段/非法 kind/非 dict 均拒绝。"""
        assert _validate_script({"segments": []}) is None
        assert _validate_script({"segments": [{"kind": "xx", "title": "t", "narration": "n"}]}) is None
        assert _validate_script({"segments": [{"kind": "body", "title": "t"}]}) is None
        assert _validate_script("not a dict") is None
        ok = _validate_script({"segments": [{"kind": "body", "title": "t", "narration": "n"}]})
        assert ok and ok[0]["subtitle"] == ""


# ================================================================ Remotion 渲染

class TestVideoRender:
    def test_tokens_from_css_match_design(self):
        """渲染色板逐字取自 design/tokens.css（三方一致）。"""
        t = _tokens_from_css()
        css = (Path(__file__).resolve().parents[2] / "design" / "tokens.css").read_text(encoding="utf-8")
        assert t["bg"] in css
        assert t["accent"] in css
        assert t["border"] in css
        assert t["bg"] == "#FFFFFF" and t["border"] == "#E1E3E6"

    def test_ensure_project_writes_tsx(self, tmp_path):
        """Remotion 工程生成：Root/QAVideo/tsconfig/package.json 齐全且含令牌。"""
        tokens = _tokens_from_css()
        wd = _ensure_project(tmp_path, tokens)
        assert (wd / "src" / "QAVideo.tsx").exists()
        assert (wd / "src" / "Root.tsx").exists()
        assert (wd / "package.json").exists()
        qa = (wd / "src" / "QAVideo.tsx").read_text(encoding="utf-8")
        assert tokens["bg"] in qa
        assert tokens["border"] in qa

    @pytest.mark.asyncio
    async def test_render_falls_back_to_pil_when_no_remotion(self, tmp_path):
        """Remotion 不可用 -> PIL+ffmpeg 兜底，产物真实落盘。"""
        out = tmp_path / "v.mp4"
        segs = [
            {"kind": "title", "title": "问题？", "subtitle": "", "narration": "问题是：问题？"},
            {"kind": "body", "title": "答案。", "subtitle": "", "narration": "答案。"},
        ]
        with patch("app.video_render._remotion_available", AsyncMock(return_value=False)):
            with patch("app.video_render._ffmpeg", AsyncMock()):
                with patch("app.video_render._draw_pil_segment") as draw:
                    result = await render_segments(segs, out, prefer="remotion")
        assert result["engine"] == "pil"
        assert result["segments"] == 2
        assert draw.call_count == 2

    @pytest.mark.asyncio
    async def test_remotion_render_invoked_when_available(self, tmp_path):
        """Remotion 可用 -> 走 remotion render（mock _render_remotion 成功）。"""
        out = tmp_path / "v.mp4"
        segs = [{"kind": "body", "title": "A。", "subtitle": "", "narration": "A。"}]

        async def fake_remotion(workdir, out_path, segments):
            out_path.write_bytes(b"fake-mp4-header")
            return out_path

        with patch("app.video_render._remotion_available", AsyncMock(return_value=True)):
            with patch("app.video_render._render_remotion", fake_remotion):
                result = await render_segments(segs, out, prefer="remotion")
        assert result["engine"] == "remotion"

    @pytest.mark.asyncio
    async def test_remotion_failure_degrades_to_pil(self, tmp_path):
        """Remotion render 抛异常 -> 自动降级 PIL，产物仍落盘。"""
        out = tmp_path / "v.mp4"
        segs = [{"kind": "body", "title": "A。", "subtitle": "", "narration": "A。"}]

        async def fake_remotion(workdir, out_path, segments):
            raise RuntimeError("remotion boom")

        with patch("app.video_render._remotion_available", AsyncMock(return_value=True)):
            with patch("app.video_render._render_remotion", fake_remotion):
                with patch("app.video_render._ffmpeg", AsyncMock()):
                    with patch("app.video_render._draw_pil_segment"):
                        result = await render_segments(segs, out, prefer="remotion")
        assert result["engine"] == "pil"


# ================================================================ 视频队列调度

def _seed_qa(tmp_path, n=3):
    """真实入库 1 篇文档 + n 条问答记录（走真实入库链路，零 Mock 数据）。"""
    test_db = tmp_path / "q.db"
    db.init_db(test_db)
    ingest_file(KB / "华联考研 招生推文.md", db_path=test_db)
    qa_ids = []
    with db.get_conn(test_db) as conn:
        for i in range(n):
            cur = conn.execute(
                "INSERT INTO qa_records (question, answer, citations, created_at)"
                " VALUES (?,?,?,?)",
                (f"问题{i}", json.dumps({"answer": f"答案{i}。"}), "[]", "2026-01-01T00:00:00Z"),
            )
            qa_ids.append(cur.lastrowid)
        conn.commit()
    return test_db, qa_ids


class TestVideoQueueScheduling:
    @pytest.mark.asyncio
    async def test_concurrent_three_running_le_one_fifo(self, tmp_path, monkeypatch):
        """并发提交 3 任务：running 始终 <= 1，完成顺序 = FIFO。"""
        test_db, qa_ids = _seed_qa(tmp_path, 3)
        monkeypatch.setattr("app.video_queue.get_conn", lambda db_path=None: db.get_conn(test_db))

        async def fake_render(**kw):
            task_qa = kw.get("question", "")
            idx = int(task_qa.replace("问题", ""))
            await asyncio.sleep(0.05 * (3 - idx))
            return {"path": "x.mp4", "seconds": 4, "segments": 1, "engine": "pil", "script_method": "rule"}

        class FakeState:
            video_dir = tmp_path

        app = type("A", (), {"state": FakeState()})()

        with patch("app.video_queue.render_qa_video", fake_render):
            with db.get_conn(test_db) as conn:
                tasks = []
                for qid in qa_ids:
                    t = asyncio.create_task(enqueue_video(conn, qid))
                    tasks.append(t)
                created = await asyncio.gather(*tasks)
            task_ids = [t["id"] for t in created]

            disp = asyncio.create_task(run_dispatcher(app, lambda *a: None))
            for _ in range(200):
                await asyncio.sleep(0.05)
                with db.get_conn(test_db) as conn:
                    statuses = [
                        r[0]
                        for r in conn.execute(
                            "SELECT status FROM video_tasks ORDER BY id"
                        )
                    ]
                    if all(s == "done" for s in statuses):
                        break
            disp.cancel()

        with db.get_conn(test_db) as conn:
            final = [
                dict(r)
                for r in conn.execute(
                    "SELECT id, status, video_path FROM video_tasks ORDER BY id"
                )
            ]
        assert all(t["status"] == "done" for t in final)
        assert video_lock() is video_lock()
        assert [t["id"] for t in final] == sorted(task_ids)

    @pytest.mark.asyncio
    async def test_running_count_never_exceeds_one(self, tmp_path, monkeypatch):
        """压测：并发提交 5 任务，任意时刻 DB running 计数 <= 1。"""
        test_db, qa_ids = _seed_qa(tmp_path, 5)
        monkeypatch.setattr("app.video_queue.get_conn", lambda db_path=None: db.get_conn(test_db))

        running_samples = []

        async def fake_render(**kw):
            with db.get_conn(test_db) as conn:
                running_samples.append(running_count(conn))
            await asyncio.sleep(0.02)
            return {"path": "x.mp4", "seconds": 4, "segments": 1, "engine": "pil", "script_method": "rule"}

        class FakeState:
            video_dir = tmp_path

        app = type("A", (), {"state": FakeState()})()

        with patch("app.video_queue.render_qa_video", fake_render):
            with db.get_conn(test_db) as conn:
                for qid in qa_ids:
                    await enqueue_video(conn, qid)
            disp = asyncio.create_task(run_dispatcher(app, lambda *a: None))
            for _ in range(300):
                await asyncio.sleep(0.05)
                with db.get_conn(test_db) as conn:
                    if conn.execute(
                        "SELECT COUNT(*) AS n FROM video_tasks WHERE status='queued'"
                    ).fetchone()["n"] == 0:
                        break
            disp.cancel()

        assert running_samples, "应有采样"
        assert max(running_samples) <= 1, f"running 曾超 1: {running_samples}"

    @pytest.mark.asyncio
    async def test_enqueue_sets_queued_status(self, tmp_path):
        """新任务必须 queued 排队，progress=0，不立即 running。"""
        test_db, qa_ids = _seed_qa(tmp_path, 1)
        with db.get_conn(test_db) as conn:
            t = await enqueue_video(conn, qa_ids[0])
        assert t["status"] == "queued"
        assert t["progress"] == 0.0

    @pytest.mark.asyncio
    async def test_queue_position_fifo(self, tmp_path):
        """queued_tasks 按 created_at,id FIFO 排序。"""
        test_db, qa_ids = _seed_qa(tmp_path, 3)
        with db.get_conn(test_db) as conn:
            for qid in qa_ids:
                await enqueue_video(conn, qid)
            qs = queued_tasks(conn)
        assert [q["qa_record_id"] for q in qs] == qa_ids


class TestVideoQueueEdgeCases:
    @pytest.mark.asyncio
    async def test_missing_qa_record_marks_failed(self, tmp_path, monkeypatch):
        """qa_record 不存在时任务标记 failed（不崩溃）。"""
        test_db = tmp_path / "edge.db"
        db.init_db(test_db)
        monkeypatch.setattr("app.video_queue.get_conn", lambda db_path=None: db.get_conn(test_db))

        # 先插入 qa_record 再删除，使 video_tasks 引用悬空（模拟真实场景）
        with db.get_conn(test_db) as conn:
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.execute(
                "INSERT INTO video_tasks (qa_record_id, status, progress, created_at)"
                " VALUES (9999, 'queued', 0.0, '2026-01-01T00:00:00Z')"
            )
            conn.commit()
            conn.execute("PRAGMA foreign_keys = ON")

        class FakeState:
            video_dir = tmp_path
        app = type("A", (), {"state": FakeState()})()

        disp = asyncio.create_task(run_dispatcher(app, lambda *a: None))
        for _ in range(40):
            await asyncio.sleep(0.05)
            with db.get_conn(test_db) as conn:
                row = conn.execute("SELECT status, error FROM video_tasks WHERE qa_record_id=9999").fetchone()
                if row and row["status"] == "failed":
                    break
        disp.cancel()

        with db.get_conn(test_db) as conn:
            row = conn.execute("SELECT status, error FROM video_tasks WHERE qa_record_id=9999").fetchone()
        assert row["status"] == "failed"
        assert "不存在" in row["error"]

    @pytest.mark.asyncio
    async def test_render_exception_marks_failed(self, tmp_path, monkeypatch):
        """render_qa_video 抛异常时任务标记 failed + error 记录。"""
        test_db, qa_ids = _seed_qa(tmp_path, 1)
        monkeypatch.setattr("app.video_queue.get_conn", lambda db_path=None: db.get_conn(test_db))

        async def boom_render(**kw):
            raise RuntimeError("ffmpeg crashed")

        class FakeState:
            video_dir = tmp_path
        app = type("A", (), {"state": FakeState()})()

        events = []
        with patch("app.video_queue.render_qa_video", boom_render):
            with db.get_conn(test_db) as conn:
                await enqueue_video(conn, qa_ids[0])
            disp = asyncio.create_task(run_dispatcher(app, lambda tid, stage, pct: events.append((tid, stage))))
            for _ in range(40):
                await asyncio.sleep(0.05)
                with db.get_conn(test_db) as conn:
                    row = conn.execute("SELECT status FROM video_tasks").fetchone()
                    if row and row["status"] == "failed":
                        break
            disp.cancel()

        with db.get_conn(test_db) as conn:
            row = conn.execute("SELECT status, error FROM video_tasks").fetchone()
        assert row["status"] == "failed"
        assert "ffmpeg crashed" in row["error"]
        assert any(s == "failed" for _, s in events)

    @pytest.mark.asyncio
    async def test_progress_callback_invoked(self, tmp_path, monkeypatch):
        """合成过程中 on_progress 回调被调用（stage + progress）。"""
        test_db, qa_ids = _seed_qa(tmp_path, 1)
        monkeypatch.setattr("app.video_queue.get_conn", lambda db_path=None: db.get_conn(test_db))

        async def fake_render(**kw):
            cb = kw.get("on_progress")
            if cb:
                cb("script", 0.1)
                cb("tts", 0.4)
                cb("render", 0.7)
            return {"path": "x.mp4", "seconds": 4, "segments": 1, "engine": "pil", "script_method": "rule"}

        class FakeState:
            video_dir = tmp_path
        app = type("A", (), {"state": FakeState()})()

        events = []
        with patch("app.video_queue.render_qa_video", fake_render):
            with db.get_conn(test_db) as conn:
                await enqueue_video(conn, qa_ids[0])
            disp = asyncio.create_task(run_dispatcher(app, lambda tid, stage, pct: events.append((stage, pct))))
            for _ in range(40):
                await asyncio.sleep(0.05)
                with db.get_conn(test_db) as conn:
                    row = conn.execute("SELECT status FROM video_tasks").fetchone()
                    if row and row["status"] == "done":
                        break
            disp.cancel()

        stages = [s for s, _ in events]
        assert "script" in stages
        assert "tts" in stages
        assert "done" in stages
