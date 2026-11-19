"""Session 3（Eval 验收）补充单测：API 层 / SSE 回调 / TTS / 视频管线 / 检索增强。

覆盖 CLAUDE.md §三 铁律 3 的覆盖率门禁（≥85%）：
- main.py：文档 CRUD（§2）、历史问答（§3）、ask SSE 契约（§6）、视频文件下载；
- sse.py：on_video_progress 事件负载（video_url / error 字段对齐前端 types）；
- tts.py：edge-tts 路径（mock 供应商 SDK 传输层，真实 ffmpeg 转码）与失败分支；
- video.py：render_qa_video 四阶段编排（mock 子管线，验证进度单调与产物落盘）；
- retrieval.py：多实体子查询分解 / 稀有词精化 / 分数降序契约。

单测允许 mock 外部服务传输层（LLM/TTS 网络、渲染子进程），但链路数据
一律走真实入库→检索→问答/队列状态机（与既有 tests/ 口径一致，非 Mock 业务数据）。
"""
from __future__ import annotations

import asyncio
import json
import wave
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import app

KB = Path(__file__).resolve().parents[2] / "知识库"
pytestmark = pytest.mark.skipif(
    not KB.is_dir(), reason="knowledge corpus not present in this checkout"
)


# ================================================================ fixtures

@pytest.fixture()
def api_client(tmp_path, monkeypatch):
    """真实建库 + 真实入库 1 篇 md，main 层全部走测试库（隔离生产 DB）。"""
    test_db = tmp_path / "api.db"
    db.init_db(test_db)
    from app.ingestion import ingest_file
    ingest_file(KB / "华联考研 招生推文.md", db_path=test_db)

    monkeypatch.setattr("app.main.get_conn", lambda db_path=None: db.get_conn(test_db))
    monkeypatch.setattr("app.retrieval.get_conn", lambda db_path=None: db.get_conn(test_db))
    # 上传走 ingest_file → ingestion.get_conn：不 patch 会把测试文档写进生产库（污染语料）
    monkeypatch.setattr("app.ingestion.get_conn", lambda db_path=None: db.get_conn(test_db))
    # lifespan 的初始入库扫描同样重定向（语料已非空会跳过，双保险）
    monkeypatch.setattr("app.main.UPLOADS_DIR", tmp_path / "uploads")
    # 视频目录隔离；调度器不启动（TestClient lifespan 会起，改为 mock render 快速完成）
    with TestClient(app) as client:
        app.state.video_dir = tmp_path / "videos"
        app.state.video_dir.mkdir(exist_ok=True)
        yield client, test_db


def _fake_llm_answer(answer="华联考研成立于 2013 年。", refusal=None):
    return {
        "answer": answer,
        "refusal_reason": refusal,
        "confidence": 0.9,
        "citations": [{"doc_id": "doc01", "para_id": "doc01#p001", "snippet": "s"}],
    }


def _sse_events(text: str) -> list[tuple[str, dict]]:
    """把 SSE 响应体解析为 (event, payload) 列表。"""
    events = []
    for block in text.split("\n\n"):
        ev, data = None, None
        for line in block.splitlines():
            if line.startswith("event:"):
                ev = line[6:].strip()
            elif line.startswith("data:"):
                data = line[5:].strip()
        if ev and data:
            events.append((ev, json.loads(data)))
    return events


# ================================================================ main.py：文档 API

class TestDocumentAPI:
    def test_list_documents_shape(self, api_client):
        client, _ = api_client
        r = client.get("/api/documents")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] >= 1
        doc = body["documents"][0]
        for key in ("doc_id", "title", "source_file", "source_format", "parse_method",
                    "char_count", "injection_flag", "chunk_count", "created_at"):
            assert key in doc

    def test_document_detail_and_404(self, api_client):
        client, _ = api_client
        doc_id = client.get("/api/documents").json()["documents"][0]["doc_id"]
        r = client.get(f"/api/documents/{doc_id}")
        assert r.status_code == 200
        assert "injection_excerpt_count" in r.json()
        r404 = client.get("/api/documents/doc99")
        assert r404.status_code == 404
        assert r404.json()["detail"]["code"] == "E_NOT_FOUND"

    def test_upload_markdown_201(self, api_client):
        client, _ = api_client
        content = "# 测试文档\n\n这是一段真实上传的内容。\n"
        r = client.post(
            "/api/documents",
            files={"file": ("测试上传.md", content.encode("utf-8"), "text/markdown")},
        )
        assert r.status_code == 201
        doc = r.json()["document"]
        assert doc["source_file"] == "测试上传.md"
        assert doc["title"] == "测试上传"
        assert doc["chunk_count"] >= 1

    def test_upload_bad_extension_422(self, api_client):
        client, _ = api_client
        r = client.post("/api/documents", files={"file": ("x.pdf", b"%PDF", "application/pdf")})
        assert r.status_code == 422
        assert r.json()["detail"]["code"] == "E_VALIDATION"

    def test_upload_unparseable_422(self, api_client):
        client, _ = api_client
        # .docx 后缀但非 ZIP → 解析失败 → E_PARSE_FAILED
        r = client.post("/api/documents", files={"file": ("坏.docx", b"not-a-zip", "application/octet-stream")})
        assert r.status_code == 422
        assert r.json()["detail"]["code"] == "E_PARSE_FAILED"

    def test_delete_document_204_then_404(self, api_client):
        client, _ = api_client
        r = client.post(
            "/api/documents",
            files={"file": ("待删.md", "# 待删\n\n内容。".encode("utf-8"), "text/markdown")},
        )
        doc_id = r.json()["document"]["doc_id"]
        assert client.delete(f"/api/documents/{doc_id}").status_code == 204
        assert client.get(f"/api/documents/{doc_id}").status_code == 404
        assert client.delete(f"/api/documents/{doc_id}").status_code == 404


# ================================================================ main.py：问答 API

class TestAskAndQaAPI:
    def test_ask_sse_contract(self, api_client, monkeypatch):
        """POST /api/ask：事件顺序与负载字段对齐 API_SPEC §6（LLM 传输层 mock）。"""
        client, test_db = api_client

        async def fake_generate(question, citations):
            return _fake_llm_answer()

        monkeypatch.setattr("app.qa.generate_answer", fake_generate)
        r = client.post("/api/ask", json={"question": "华联考研哪年成立？"})
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        events = _sse_events(r.text)
        names = [e for e, _ in events]
        assert names.index("qa.progress") < names.index("qa.citations")
        assert names.index("qa.citations") < names.index("qa.answer")
        assert names.index("qa.answer") < names.index("qa.done")
        assert names.index("qa.done") < names.index("video.queued")
        # qa.citations 四件套 + doc_title/source_file
        cites = next(p for e, p in events if e == "qa.citations")["citations"]
        assert cites and all(c.get("para_id") and c.get("heading_path") is not None for c in cites)
        # qa.done 回填 video_task_id；video.queued 携带真实 FIFO 位置
        done = next(p for e, p in events if e == "qa.done")
        queued = next(p for e, p in events if e == "video.queued")
        assert isinstance(done["qa_record_id"], int)
        assert done["video_task_id"] == queued["task_id"]
        assert queued["queue_position"] >= 1
        assert done["refusal_reason"] is None
        # qa_records.video_task_id 已回填
        with db.get_conn(test_db) as conn:
            row = conn.execute(
                "SELECT video_task_id FROM qa_records WHERE id=?", (done["qa_record_id"],)
            ).fetchone()
        assert row["video_task_id"] == done["video_task_id"]

    def test_ask_llm_failure_degrades_safely(self, api_client, monkeypatch):
        client, _ = api_client

        async def boom(question, citations):
            raise RuntimeError("llm down")

        monkeypatch.setattr("app.qa.generate_answer", boom)
        r = client.post("/api/ask", json={"question": "任意问题？"})
        events = _sse_events(r.text)
        done = next(p for e, p in events if e == "qa.done")
        assert done["refusal_reason"].startswith("E_LLM_FAILED")
        answer_text = "".join(p["delta"] for e, p in events if e == "qa.answer")
        assert "知识库未覆盖" in answer_text

    def test_qa_list_and_detail(self, api_client, monkeypatch):
        client, _ = api_client

        async def fake_generate(question, citations):
            return _fake_llm_answer(answer="答案正文一二三。")

        monkeypatch.setattr("app.qa.generate_answer", fake_generate)
        client.post("/api/ask", json={"question": "华联考研哪年成立？"})

        lst = client.get("/api/qa").json()
        assert lst["total"] >= 1
        rec = lst["records"][0]
        # answer_summary 是纯文本摘要（非 JSON 原文）
        assert not rec["answer_summary"].startswith("{")
        assert rec["video_status"] in ("queued", "running", "done", "failed", None)

        detail = client.get(f"/api/qa/{rec['id']}").json()["record"]
        assert detail["answer"] == "答案正文一二三。"
        assert detail["refusal_reason"] is None
        assert isinstance(detail["citations"], list)
        assert client.get("/api/qa/99999").status_code == 404

    def test_video_tasks_endpoints(self, api_client, monkeypatch):
        client, test_db = api_client

        async def fake_generate(question, citations):
            return _fake_llm_answer()

        monkeypatch.setattr("app.qa.generate_answer", fake_generate)
        r = client.post("/api/ask", json={"question": "问题？"})
        events = _sse_events(r.text)
        tid = next(p for e, p in events if e == "qa.done")["video_task_id"]

        lst = client.get("/api/video-tasks").json()
        assert "running_count" in lst
        detail = client.get(f"/api/video-tasks/{tid}").json()["task"]
        assert detail["id"] == tid
        assert client.get("/api/video-tasks/99999").json()["error"]["code"] == "E_NOT_FOUND"
        # 未就绪视频 → E_NOT_FOUND
        assert client.get(f"/api/videos/{tid}/file").json()["error"]["code"] == "E_NOT_FOUND"
        # done + 落盘后可下载
        video = app.state.video_dir / "t.mp4"
        video.write_bytes(b"\x00\x00\x00\x18ftypmp42fake")
        with db.get_conn(test_db) as conn:
            conn.execute("UPDATE video_tasks SET status='done', video_path=? WHERE id=?",
                         (str(video), tid))
            conn.commit()
        rf = client.get(f"/api/videos/{tid}/file")
        assert rf.status_code == 200
        assert rf.headers["content-type"] == "video/mp4"
        assert client.get("/api/videos/99999/file").json()["error"]["code"] == "E_NOT_FOUND"


# ================================================================ sse.py

class TestSseCallbacks:
    @pytest.mark.asyncio
    async def test_broadcast_fanout(self):
        from app import sse
        q1, q2 = asyncio.Queue(), asyncio.Queue()
        sse._subs.update({q1, q2})
        try:
            await sse.broadcast("x", {"a": 1})
            assert q1.get_nowait() == ("x", {"a": 1})
            assert q2.get_nowait() == ("x", {"a": 1})
        finally:
            sse._subs.difference_update({q1, q2})

    @pytest.mark.asyncio
    async def test_on_video_progress_done_carries_url(self, tmp_path, monkeypatch):
        from app import sse
        test_db = tmp_path / "s.db"
        db.init_db(test_db)
        with db.get_conn(test_db) as conn:
            conn.execute("INSERT INTO qa_records (question, answer, citations, created_at)"
                         " VALUES ('q','{}','[]','t')")
            cur = conn.execute("INSERT INTO video_tasks (qa_record_id, status, video_path, created_at)"
                               " VALUES (1,'done','x.mp4','t')")
            tid = cur.lastrowid
            conn.commit()
        monkeypatch.setattr("app.sse.get_conn", lambda db_path=None: db.get_conn(test_db))
        q = asyncio.Queue()
        sse._subs.add(q)
        try:
            sse.on_video_progress(tid, "done", 1.0)
            ev, data = await asyncio.wait_for(q.get(), timeout=2.0)
            assert ev == "video.done"
            assert data["video_url"] == f"/api/videos/{tid}/file"
            assert data["progress"] == 1.0
        finally:
            sse._subs.discard(q)

    @pytest.mark.asyncio
    async def test_on_video_progress_failed_carries_error(self, tmp_path, monkeypatch):
        from app import sse
        test_db = tmp_path / "s.db"
        db.init_db(test_db)
        with db.get_conn(test_db) as conn:
            conn.execute("INSERT INTO qa_records (question, answer, citations, created_at)"
                         " VALUES ('q','{}','[]','t')")
            cur = conn.execute("INSERT INTO video_tasks (qa_record_id, status, error, created_at)"
                               " VALUES (1,'failed','ffmpeg boom','t')")
            tid = cur.lastrowid
            conn.commit()
        monkeypatch.setattr("app.sse.get_conn", lambda db_path=None: db.get_conn(test_db))
        q = asyncio.Queue()
        sse._subs.add(q)
        try:
            sse.on_video_progress(tid, "failed", 1.0)
            ev, data = await asyncio.wait_for(q.get(), timeout=2.0)
            assert ev == "video.failed"
            assert data["error"] == "ffmpeg boom"
        finally:
            sse._subs.discard(q)

    @pytest.mark.asyncio
    async def test_on_video_progress_running(self, monkeypatch):
        from app import sse
        q = asyncio.Queue()
        sse._subs.add(q)
        try:
            sse.on_video_progress(7, "tts", 0.34567)
            ev, data = await asyncio.wait_for(q.get(), timeout=2.0)
            assert ev == "video.progress"
            assert data == {"task_id": 7, "stage": "tts", "progress": 0.3457}
        finally:
            sse._subs.discard(q)


# ================================================================ tts.py

def _write_wav(path: Path, seconds: float = 0.2, sr: int = 24000):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b"\x00\x00" * int(sr * seconds))


class TestTts:
    @pytest.mark.asyncio
    async def test_empty_text_raises(self, tmp_path):
        from app.tts import TTSError, synth
        with pytest.raises(TTSError):
            await synth("   ", tmp_path / "x.wav")

    @pytest.mark.asyncio
    async def test_unknown_provider_raises(self, tmp_path, monkeypatch):
        from app.config import settings
        from app.tts import TTSError, synth
        monkeypatch.setattr(settings, "tts_provider", "no-such")
        with pytest.raises(TTSError):
            await synth("你好", tmp_path / "x.wav")

    @pytest.mark.asyncio
    async def test_openai_provider_missing_key(self, tmp_path, monkeypatch):
        from app.config import settings
        from app.tts import TTSError, synth
        monkeypatch.setattr(settings, "tts_provider", "openai")
        monkeypatch.setattr(settings, "openai_tts_api_key", "")
        with pytest.raises(TTSError):
            await synth("你好", tmp_path / "x.wav")

    @pytest.mark.asyncio
    async def test_edge_tts_path_real_ffmpeg(self, tmp_path, monkeypatch):
        """mock edge-tts SDK 传输层（写真实 WAV），ffmpeg 转码真实执行。"""
        from app import tts as tts_mod

        class FakeCommunicate:
            def __init__(self, text, voice=None):
                self.text, self.voice = text, voice

            async def save(self, out):
                _write_wav(Path(out), seconds=0.3, sr=24000)

        import edge_tts
        monkeypatch.setattr(edge_tts, "Communicate", FakeCommunicate)
        out = tmp_path / "seg.wav"
        info = await tts_mod.synth("真实合成文本", out)
        assert info["format"] == "edge-tts"
        assert info["sample_rate"] == 24000
        assert info["channels"] == 1
        assert 0.2 <= info["seconds"] <= 0.5
        assert out.exists() and out.stat().st_size > 1000


# ================================================================ video.py

class TestVideoOrchestration:
    @pytest.mark.asyncio
    async def test_render_qa_video_stages_and_mux(self, tmp_path, monkeypatch):
        """四阶段编排：script→tts→render→mux；逐页 TTS 时长驱动帧数；进度单调不减。"""
        from app import video as video_mod

        pages = [
            {"kind": "question", "label": "问题检索", "title": "问？", "meta": "m", "narration": "问题是：问"},
            {"kind": "answer", "label": "核心解答", "recap": "问？", "summary": "答。",
             "points": ["要点"], "narration": "答。"},
            {"kind": "citations", "label": "引用参考文档", "citations": [], "narration": "无引用。"},
        ]

        async def fake_script(q, a, c):
            return pages, "rule"

        async def fake_synth(text, wav, **kw):
            _write_wav(Path(wav), seconds=0.5)
            return {"seconds": 0.5, "format": "edge-tts", "voice": "v",
                    "sample_rate": 24000, "channels": 1, "bytes": 100}

        seen = {}

        async def fake_render(render_pages_arg, out_path, prefer="remotion"):
            seen["frames"] = [p.get("frames") for p in render_pages_arg]
            seen["durations"] = [p.get("duration") for p in render_pages_arg]
            # 真实无声底片：总时长 = 各页帧数之和 / 24
            total = sum(p["frames"] for p in render_pages_arg) / 24
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=white:s=320x240:d={total}:r=24",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out_path),
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            await proc.wait()
            assert proc.returncode == 0
            return {"path": str(out_path), "seconds": total, "engine": "pil"}

        monkeypatch.setattr(video_mod, "build_video_script", fake_script)
        monkeypatch.setattr(video_mod, "synth", fake_synth)
        monkeypatch.setattr(video_mod, "render_pages", fake_render)

        progress = []
        out = tmp_path / "qa_video.mp4"
        result = await video_mod.render_qa_video(
            question="问？", answer="答。", citations=[], out_path=out,
            on_progress=lambda s, p: progress.append((s, p)),
        )
        assert out.exists() and out.stat().st_size > 1000
        assert result["segments"] == 3 and result["pages"] == 3
        assert result["stages"] == ["script", "tts", "render", "mux"]
        assert result["script_method"] == "rule"
        # 每页帧数 = (语音 0.5s + 呼吸停顿 0.4s) × 24 ≈ 22 帧
        assert seen["frames"] == [22, 22, 22]
        assert all(abs(d - 22 / 24) < 1e-3 for d in seen["durations"])
        # 成片总时长 = 66 帧 / 24fps = 2.75s（三页完整播完，不因音轨截断）
        assert abs(result["seconds"] - 2.75) < 0.05
        pcts = [p for _, p in progress]
        assert pcts == sorted(pcts)  # 单调不减
        assert pcts[-1] == 1.0
        stages = [s for s, _ in progress]
        assert stages[0] == "script" and stages[-1] == "mux"

    @pytest.mark.asyncio
    async def test_ffmpeg_failure_raises(self):
        from app.video import _ffmpeg
        with pytest.raises(RuntimeError, match="ffmpeg"):
            await _ffmpeg("-i", "no-such-file-xyz.mp4", "-y", "out.mp4")


# ================================================================ retrieval 增强

class TestRetrievalEnhancements:
    def test_split_subqueries_entities(self):
        from app.retrieval import split_subqueries
        subs = split_subqueries("众赢科技和澎湃教育的研发团队规模差多少？")
        assert "众赢科技" in subs
        assert any("澎湃教育" in s for s in subs)

    def test_split_subqueries_single_entity(self):
        from app.retrieval import split_subqueries
        # 无多实体分解价值时子查询不改变主查询语义
        assert split_subqueries("") == []

    def test_rare_term_queries_finds_cto(self, tmp_path, monkeypatch):
        from app.retrieval import rare_term_queries
        test_db = tmp_path / "r.db"
        db.init_db(test_db)
        from app.ingestion import load_initial_corpus
        load_initial_corpus(KB, db_path=test_db)
        monkeypatch.setattr("app.retrieval.get_conn", lambda db_path=None: db.get_conn(test_db))
        rare = rare_term_queries("澎湃教育的 CTO 是谁？")
        assert any("CTO" in q for q in rare)

    def test_multi_entity_topk_covers_both_docs(self, tmp_path, monkeypatch):
        """通用机制验证：A 和 B 对比问题，两实体文档都进 Top-K。"""
        from app.retrieval import hybrid_search
        test_db = tmp_path / "r.db"
        db.init_db(test_db)
        from app.ingestion import load_initial_corpus
        load_initial_corpus(KB, db_path=test_db)
        monkeypatch.setattr("app.retrieval.get_conn", lambda db_path=None: db.get_conn(test_db))
        hits = hybrid_search("众赢科技和澎湃教育的研发团队规模差多少？", top_k=5)
        docs = {h["doc_id"] for h in hits}
        assert {"doc05", "doc06"} <= docs
        scores = [h["score"] for h in hits]
        assert scores == sorted(scores, reverse=True)

    def test_citation_fields_complete(self, tmp_path, monkeypatch):
        from app.retrieval import hybrid_search
        test_db = tmp_path / "r.db"
        db.init_db(test_db)
        from app.ingestion import load_initial_corpus
        load_initial_corpus(KB, db_path=test_db)
        monkeypatch.setattr("app.retrieval.get_conn", lambda db_path=None: db.get_conn(test_db))
        for h in hybrid_search("众赢科技研发投入", top_k=5):
            assert h["doc_title"] and h["source_file"]
            assert h["para_id"].startswith(h["doc_id"])

    def test_source_file_of(self, tmp_path):
        from app.retrieval import source_file_of
        test_db = tmp_path / "r.db"
        db.init_db(test_db)
        from app.ingestion import ingest_file
        ingest_file(KB / "华联考研 招生推文.md", db_path=test_db)
        with db.get_conn(test_db) as conn:
            assert source_file_of(conn, "doc01") == "华联考研 招生推文.md"
            assert source_file_of(conn, "doc99") == "doc99"


# ================================================================ qa.py 重试

class TestQaRetry:
    @pytest.mark.asyncio
    async def test_retry_on_transient_failure(self, monkeypatch):
        """LLM 首次 429 → 退避重试 → 第二次成功（传输层 mock，重试逻辑真实）。"""
        from app.config import settings
        from app.qa import generate_answer
        monkeypatch.setattr(settings, "llm_api_key", "k", raising=False)
        monkeypatch.setattr(settings, "llm_base_url", "http://x", raising=False)
        monkeypatch.setattr(settings, "llm_model", "m", raising=False)

        calls = {"n": 0}

        class FakeResp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"choices": [{"message": {"content": json.dumps(_fake_llm_answer())}}]}

        async def flaky_post(self, url, json=None, headers=None):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("429 Too Many Requests")
            return FakeResp()

        monkeypatch.setattr("httpx.AsyncClient.post", flaky_post)
        with patch("app.qa.asyncio.sleep", AsyncMock()):
            result = await generate_answer("Q", [])
        assert calls["n"] == 2
        assert result["refusal_reason"] is None
        assert "2013" in result["answer"]

    @pytest.mark.asyncio
    async def test_retry_exhausted_raises(self, monkeypatch):
        from app.config import settings
        from app.qa import generate_answer
        monkeypatch.setattr(settings, "llm_api_key", "k", raising=False)
        monkeypatch.setattr(settings, "llm_base_url", "http://x", raising=False)
        monkeypatch.setattr(settings, "llm_model", "m", raising=False)

        async def always_fail(self, url, json=None, headers=None):
            raise RuntimeError("429")

        monkeypatch.setattr("httpx.AsyncClient.post", always_fail)
        with patch("app.qa.asyncio.sleep", AsyncMock()):
            with pytest.raises(RuntimeError, match="429"):
                await generate_answer("Q", [])

    def test_looks_truncated_heuristic(self):
        """句中断尾启发式：逗号/连词/未闭合括号收尾视为可疑。"""
        from app.qa import _looks_truncated
        assert _looks_truncated("华联考研在招生推文中明确表示，把") is True
        assert _looks_truncated("答案写到一半，") is True
        assert _looks_truncated("（网名") is True
        assert _looks_truncated("完整的答案。") is False
        assert _looks_truncated("") is False

    @pytest.mark.asyncio
    async def test_suspicious_answer_retried(self, monkeypatch):
        """合法 JSON 但句中断尾 → 重试后得到完整答案。"""
        from app.config import settings
        from app.qa import generate_answer
        monkeypatch.setattr(settings, "llm_api_key", "k", raising=False)
        monkeypatch.setattr(settings, "llm_base_url", "http://x", raising=False)
        monkeypatch.setattr(settings, "llm_model", "m", raising=False)

        calls = {"n": 0}

        class FakeResp:
            def __init__(self, answer):
                self.answer = answer

            def raise_for_status(self):
                pass

            def json(self):
                return {"choices": [{
                    "finish_reason": "stop",
                    "message": {"content": json.dumps(_fake_llm_answer(answer=self.answer))},
                }]}

        async def flaky(self, url, json=None, headers=None):
            calls["n"] += 1
            return FakeResp("写到一半，把" if calls["n"] == 1 else "完整的一句话。")

        monkeypatch.setattr("httpx.AsyncClient.post", flaky)
        result = await generate_answer("Q", [])
        assert calls["n"] == 2
        assert result["answer"] == "完整的一句话。"

    @pytest.mark.asyncio
    async def test_truncated_output_retries_with_larger_budget(self, monkeypatch):
        """finish_reason=length（输出截断）→ 提升 max_tokens 重试 → 完整答案。"""
        from app.config import settings
        from app.qa import generate_answer
        monkeypatch.setattr(settings, "llm_api_key", "k", raising=False)
        monkeypatch.setattr(settings, "llm_base_url", "http://x", raising=False)
        monkeypatch.setattr(settings, "llm_model", "m", raising=False)
        monkeypatch.setattr(settings, "llm_max_tokens", 128, raising=False)

        calls = {"n": 0, "budgets": []}

        class FakeResp:
            def __init__(self, finish):
                self.finish = finish

            def raise_for_status(self):
                pass

            def json(self):
                return {"choices": [{
                    "finish_reason": self.finish,
                    "message": {"content": json.dumps(_fake_llm_answer(answer="完整答案。"))},
                }]}

        async def truncating_post(self, url, json=None, headers=None):
            calls["n"] += 1
            calls["budgets"].append(json.get("max_tokens"))
            if calls["n"] == 1:
                return FakeResp("length")
            return FakeResp("stop")

        monkeypatch.setattr("httpx.AsyncClient.post", truncating_post)
        result = await generate_answer("Q", [])
        assert calls["n"] == 2
        assert calls["budgets"][1] == 256  # 截断后 max_tokens ×2
        assert result["answer"] == "完整答案。"

    @pytest.mark.asyncio
    async def test_empty_refusal_normalized_to_none(self, monkeypatch):
        from app.config import settings
        from app.qa import generate_answer
        monkeypatch.setattr(settings, "llm_api_key", "k", raising=False)
        monkeypatch.setattr(settings, "llm_base_url", "http://x", raising=False)
        monkeypatch.setattr(settings, "llm_model", "m", raising=False)

        class FakeResp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"choices": [{"message": {"content": json.dumps(
                    {"answer": "a", "refusal_reason": "", "confidence": 0.8})}}]}

        async def ok_post(self, url, json=None, headers=None):
            return FakeResp()

        monkeypatch.setattr("httpx.AsyncClient.post", ok_post)
        result = await generate_answer("Q", [])
        assert result["refusal_reason"] is None


# ================================================================ video_render PIL 路径

class TestPilRenderReal:
    @pytest.mark.asyncio
    async def test_pil_render_real_frames_and_duration(self, tmp_path):
        """PIL 真实渲染：逐帧 PNG 数=总帧数、时长=帧数/24、out_path 落盘。"""
        from app.video_render import render_pages
        pages = [
            {"kind": "question", "label": "问题检索", "title": "问题标题" * 8,
             "meta": "知识库检索", "narration": "n", "frames": 12},
            {"kind": "answer", "label": "核心解答", "recap": "问题？",
             "summary": "结论包含 75% 与 11 亿元。", "points": ["要点一", "要点二"],
             "narration": "n", "frames": 18},
            {"kind": "citations", "label": "引用参考文档",
             "citations": [{"source_file": "f.docx", "heading_path": "h > s", "snippet": "摘录"}],
             "narration": "n", "frames": 10},
        ]
        out = tmp_path / "pil.mp4"
        result = await render_pages(pages, out, prefer="pil")
        assert result["engine"] == "pil"
        assert out.exists() and out.stat().st_size > 1000
        frames = list((out.with_suffix(".parts") / "frames").glob("frame*.png"))
        assert len(frames) == 12 + 18 + 10
        # ffprobe 时长 ≈ 40/24 ≈ 1.667s
        proc = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=nw=1:nk=1", str(out),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        stdout, _ = await proc.communicate()
        assert abs(float(stdout.decode().strip()) - 40 / 24) < 0.15


class TestTtsRetry:
    @pytest.mark.asyncio
    async def test_edge_tts_retries_with_backoff(self, tmp_path, monkeypatch):
        """edge-tts 偶发断连：1s/2s 两次指数退避后成功。"""
        from app import tts as tts_mod
        from app.config import settings

        monkeypatch.setattr(settings, "tts_provider", "edge-tts")
        delays: list[float] = []

        async def fake_sleep(d):
            delays.append(d)

        monkeypatch.setattr("app.tts.asyncio.sleep", fake_sleep)
        calls = {"n": 0}

        class Flaky:
            def __init__(self, text, voice=None):
                pass

            async def save(self, out):
                calls["n"] += 1
                if calls["n"] < 3:
                    raise ConnectionError("connection reset")
                _write_wav(Path(out), seconds=0.2, sr=24000)

        import edge_tts
        monkeypatch.setattr(edge_tts, "Communicate", Flaky)
        out = tmp_path / "retry.wav"
        info = await tts_mod.synth("重试测试", out)
        assert calls["n"] == 3
        assert delays == [1, 2]
        assert info["format"] == "edge-tts"
        assert out.exists()

    @pytest.mark.asyncio
    async def test_edge_tts_retries_exhausted_raises(self, tmp_path, monkeypatch):
        """两次重试仍失败 → 抛出原异常。"""
        from app import tts as tts_mod
        from app.config import settings

        monkeypatch.setattr(settings, "tts_provider", "edge-tts")
        delays: list[float] = []

        async def fake_sleep(d):
            delays.append(d)

        monkeypatch.setattr("app.tts.asyncio.sleep", fake_sleep)

        class AlwaysFail:
            def __init__(self, text, voice=None):
                pass

            async def save(self, out):
                raise ConnectionError("down")

        import edge_tts
        monkeypatch.setattr(edge_tts, "Communicate", AlwaysFail)
        with pytest.raises(ConnectionError):
            await tts_mod.synth("始终失败", tmp_path / "x.wav")
        assert delays == [1, 2]
