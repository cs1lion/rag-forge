"""RAG 范围隔离与风险提示汇总（本次增量需求）。

覆盖：
- selected_doc_ids 范围隔离：None=全部、[]=不选用、非空列表=严格限定；
- 问答 SSE 返回汇总 risk_warnings（涉及文档去重）；
- 取消 XML 强隔离后的上下文拼装（普通文本 + 四维溯源）。
"""
from __future__ import annotations

import json
import json as jsonlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import app
from app.qa import build_context

KB = Path(__file__).resolve().parents[2] / "知识库"
pytestmark = pytest.mark.skipif(
    not KB.is_dir(), reason="knowledge corpus not present in this checkout"
)


@pytest.fixture()
def seeded_db(tmp_path, monkeypatch):
    test_db = tmp_path / "rag.db"
    db.init_db(test_db)
    from app.ingestion import load_initial_corpus
    load_initial_corpus(KB, db_path=test_db)
    factory = lambda db_path=None: db.get_conn(test_db)
    monkeypatch.setattr("app.retrieval.get_conn", factory)
    return test_db


@pytest.fixture()
def api_client(tmp_path, monkeypatch):
    """API 级：测试库 + 真实入库；调度器 no-op（避免真实合成耗时）。"""
    test_db = tmp_path / "rag_api.db"
    db.init_db(test_db)
    from app.ingestion import load_initial_corpus
    load_initial_corpus(KB, db_path=test_db)
    factory = lambda db_path=None: db.get_conn(test_db)
    monkeypatch.setattr("app.main.get_conn", factory)
    monkeypatch.setattr("app.retrieval.get_conn", factory)
    monkeypatch.setattr("app.ingestion.get_conn", factory)
    monkeypatch.setattr("app.video_queue.get_conn", factory)
    monkeypatch.setattr("app.main.UPLOADS_DIR", tmp_path / "uploads")

    async def _noop_dispatcher(app_, on_progress):
        import asyncio
        while True:
            await asyncio.sleep(0.05)

    monkeypatch.setattr("app.main.run_dispatcher", _noop_dispatcher)

    async def fake_answer(question, citations):
        return {
            "answer": "基于选中文档的回答。",
            "refusal_reason": None,
            "confidence": 0.9,
            "citations": citations,
        }

    monkeypatch.setattr("app.qa.generate_answer", fake_answer)

    with TestClient(app) as client:
        app.state.video_dir = tmp_path / "videos"
        app.state.video_dir.mkdir(parents=True, exist_ok=True)
        yield client, test_db


def _sse_events(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.split("\n\n"):
        ev = data = None
        for line in block.splitlines():
            if line.startswith("event:"):
                ev = line[6:].strip()
            elif line.startswith("data:"):
                data = line[5:].strip()
        if ev and data:
            events.append((ev, json.loads(data)))
    return events


# ---------------------------------------------------------------- 检索范围隔离

class TestSelectedDocScope:
    def test_none_means_all_docs(self, seeded_db):
        from app.retrieval import hybrid_search
        hits = hybrid_search("众赢科技研发投入", top_k=10, doc_ids=None)
        assert hits
        assert len({h["doc_id"] for h in hits}) >= 1

    def test_single_doc_scope_strict(self, seeded_db):
        from app.retrieval import hybrid_search
        hits = hybrid_search("众赢科技研发投入", top_k=10, doc_ids=["doc05"])
        assert hits
        assert {h["doc_id"] for h in hits} == {"doc05"}

    def test_empty_scope_returns_nothing(self, seeded_db):
        from app.retrieval import hybrid_search
        assert hybrid_search("众赢科技研发投入", top_k=10, doc_ids=[]) == []

    def test_out_of_scope_doc_never_recalled(self, seeded_db):
        """问题命中 doc02 但只选 doc05：范围外文档不得出现在结果中。"""
        from app.retrieval import hybrid_search
        hits = hybrid_search("华联考研 招生 自习室", top_k=10, doc_ids=["doc05"])
        assert all(h["doc_id"] == "doc05" for h in hits)

    def test_unknown_doc_scope_returns_nothing(self, seeded_db):
        from app.retrieval import hybrid_search
        assert hybrid_search("众赢科技", top_k=10, doc_ids=["doc99"]) == []


# ---------------------------------------------------------------- API 范围与风险汇总

class TestAskScopeAndRiskWarnings:
    def test_ask_respects_selected_doc_ids(self, api_client):
        client, _ = api_client
        r = client.post(
            "/api/qa/ask",
            json={"question": "众赢科技小不点机器人", "selected_doc_ids": ["doc05"]},
        )
        assert r.status_code == 200, r.text
        events = _sse_events(r.text)
        cites = next(d for e, d in events if e == "qa.citations")
        assert cites["citations"], "选中文档内应有召回"
        assert {c["doc_id"] for c in cites["citations"]} == {"doc05"}
        # 风险提示汇总：doc05 含注入特征 → 返回 risk_warnings
        assert cites["risk_warnings"]
        assert cites["risk_warnings"][0]["doc_id"] == "doc05"
        assert cites["risk_warnings"][0]["risk_warning"] == (
            "检测到疑似提示词注入指令，已在解析阶段自动过滤"
        )

    def test_ask_empty_scope_no_citations_and_skips_video(self, api_client):
        client, test_db = api_client
        r = client.post(
            "/api/qa/ask", json={"question": "众赢科技", "selected_doc_ids": []}
        )
        events = _sse_events(r.text)
        cites = next(d for e, d in events if e == "qa.citations")
        assert cites["citations"] == []
        assert cites["risk_warnings"] == []
        # 空范围 = 拒答：不进入合成队列，任务标记 skipped
        assert not any(e == "video.queued" for e, _ in events)
        skipped = next(d for e, d in events if e == "video.skipped")
        assert skipped["reason"] == "知识库未命中，已跳过视频生成"
        with db.get_conn(test_db) as conn:
            row = conn.execute(
                "SELECT status, stage_text, video_path FROM video_tasks"
                " WHERE id = ?", (skipped["task_id"],)
            ).fetchone()
        assert row["status"] == "skipped"
        assert row["stage_text"] == "知识库未命中，已跳过视频生成"
        assert row["video_path"] is None

    def test_refusal_skips_video_generation(self, api_client, monkeypatch):
        """知识库外拒答（refusal_reason 非空）不触发视频合成。"""
        client, test_db = api_client

        async def refusal_answer(question, citations):
            return {
                "answer": "知识库未覆盖该问题。",
                "refusal_reason": "E_OUT_OF_KNOWLEDGE",
                "confidence": 0.0,
                "citations": [],
            }

        monkeypatch.setattr("app.qa.generate_answer", refusal_answer)
        r = client.post(
            "/api/qa/ask", json={"question": "域外问题", "selected_doc_ids": ["doc05"]}
        )
        events = _sse_events(r.text)
        assert not any(e == "video.queued" for e, _ in events)
        skipped = next(d for e, d in events if e == "video.skipped")
        with db.get_conn(test_db) as conn:
            row = conn.execute(
                "SELECT status, stage_text FROM video_tasks WHERE id = ?",
                (skipped["task_id"],),
            ).fetchone()
            running = conn.execute(
                "SELECT COUNT(*) AS n FROM video_tasks WHERE status='running'"
            ).fetchone()["n"]
        assert row["status"] == "skipped"
        assert running == 0

    def test_normal_answer_still_queues_video(self, api_client):
        client, test_db = api_client
        r = client.post(
            "/api/qa/ask", json={"question": "众赢科技", "selected_doc_ids": ["doc05"]}
        )
        events = _sse_events(r.text)
        assert any(e == "video.queued" for e, _ in events)
        assert not any(e == "video.skipped" for e, _ in events)
        with db.get_conn(test_db) as conn:
            st = conn.execute("SELECT status FROM video_tasks").fetchone()["status"]
        assert st == "queued"

    def test_ask_legacy_doc_ids_alias(self, api_client):
        """旧字段 doc_ids 仍生效（selected_doc_ids 缺省时）。"""
        client, _ = api_client
        r = client.post(
            "/api/qa/ask", json={"question": "众赢科技", "doc_ids": ["doc05"]}
        )
        events = _sse_events(r.text)
        cites = next(d for e, d in events if e == "qa.citations")
        assert {c["doc_id"] for c in cites["citations"]} == {"doc05"}

    def test_selected_doc_ids_takes_precedence(self, api_client):
        client, _ = api_client
        r = client.post(
            "/api/qa/ask",
            json={
                "question": "众赢科技",
                "selected_doc_ids": ["doc05"],
                "doc_ids": ["doc02"],
            },
        )
        events = _sse_events(r.text)
        cites = next(d for e, d in events if e == "qa.citations")
        assert {c["doc_id"] for c in cites["citations"]} == {"doc05"}

    def test_risk_warnings_deduped_per_doc(self, api_client):
        """同一文档多段命中时 risk_warnings 只汇总一次。"""
        client, _ = api_client
        r = client.post(
            "/api/qa/ask",
            json={"question": "众赢科技 研发 小不点 智慧校园", "selected_doc_ids": ["doc05"]},
        )
        events = _sse_events(r.text)
        cites = next(d for e, d in events if e == "qa.citations")
        doc_ids = [x["doc_id"] for x in cites["risk_warnings"]]
        assert len(doc_ids) == len(set(doc_ids))

    def test_ask_alias_route_and_plain_route(self, api_client):
        client, _ = api_client
        assert client.post("/api/qa/ask", json={"question": "q", "selected_doc_ids": []}).status_code == 200
        assert client.post("/api/ask", json={"question": "q", "selected_doc_ids": []}).status_code == 200


# ---------------------------------------------------------------- 上下文拼装

class TestContextAssembly:
    def test_context_plain_text_with_four_dim(self):
        ctx = build_context(
            [{"doc_id": "doc05", "source_file": "a.docx", "heading_path": "h",
              "para_id": "doc05#p041", "snippet": "研发投入 11 亿元"}]
        )
        assert "<retrieved_documents>" not in ctx
        for token in ("doc05", "a.docx", "h", "doc05#p041", "研发投入 11 亿元"):
            assert token in ctx

    def test_context_empty(self):
        assert "<retrieved_documents>" not in build_context([])


# ---------------------------------------------------------------- LLM 重试与截断

class _Resp:
    def __init__(self, content: str, finish_reason=None):
        self._content = content
        self._finish = finish_reason

    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"message": {"content": self._content},
                             "finish_reason": self._finish}]}


def _set_llm(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "llm_api_key", "k", raising=False)
    monkeypatch.setattr(settings, "llm_base_url", "http://x", raising=False)
    monkeypatch.setattr(settings, "llm_model", "m", raising=False)
    monkeypatch.setattr(settings, "llm_max_tokens", 256, raising=False)


class TestQaRetryAndTruncation:
    def test_looks_truncated(self):
        from app.qa import _looks_truncated
        assert _looks_truncated("答案说到一半，") is True
        assert _looks_truncated("（未闭合") is True
        assert _looks_truncated("完整答案。") is False
        assert _looks_truncated("") is False

    @pytest.mark.asyncio
    async def test_finish_reason_length_retries_then_success(self, monkeypatch):
        from app.qa import generate_answer
        _set_llm(monkeypatch)
        calls = {"n": 0}

        async def fake_post(self, url, json=None, headers=None):
            calls["n"] += 1
            if calls["n"] == 1:
                return _Resp("{}", finish_reason="length")
            return _Resp(jsonlib.dumps({"answer": "完整答案。", "confidence": 0.9,
                                     "citations": [], "refusal_reason": None}))

        monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
        out = await generate_answer("Q", [])
        assert out["answer"] == "完整答案。"
        assert calls["n"] == 2

    @pytest.mark.asyncio
    async def test_suspicious_truncation_retries_then_success(self, monkeypatch):
        from app.qa import generate_answer
        _set_llm(monkeypatch)
        calls = {"n": 0}

        async def fake_post(self, url, json=None, headers=None):
            calls["n"] += 1
            if calls["n"] == 1:
                return _Resp(jsonlib.dumps({"answer": "说到一半，"}))
            return _Resp(jsonlib.dumps({"answer": "完整答案。", "confidence": 0.8,
                                     "citations": [], "refusal_reason": None}))

        monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
        out = await generate_answer("Q", [])
        assert out["answer"] == "完整答案。"
        assert calls["n"] == 2

    @pytest.mark.asyncio
    async def test_gateway_error_backoff_then_success(self, monkeypatch):
        from app.qa import generate_answer
        _set_llm(monkeypatch)
        calls = {"n": 0}

        async def fake_sleep(_):
            return None

        async def fake_post(self, url, json=None, headers=None):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("429 rate limited")
            return _Resp(jsonlib.dumps({"answer": "恢复后答案。", "confidence": 0.7,
                                     "citations": [], "refusal_reason": None}))

        monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
        monkeypatch.setattr("app.qa.asyncio.sleep", fake_sleep)
        out = await generate_answer("Q", [])
        assert out["answer"] == "恢复后答案。"
        assert calls["n"] == 2

    @pytest.mark.asyncio
    async def test_retry_exhausted_raises(self, monkeypatch):
        from app.qa import generate_answer
        _set_llm(monkeypatch)

        async def fake_post(self, url, json=None, headers=None):
            return _Resp("{}", finish_reason="length")

        monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
        with pytest.raises(RuntimeError):
            await generate_answer("Q", [])

    @pytest.mark.asyncio
    async def test_empty_refusal_normalized_to_null(self, monkeypatch):
        from app.qa import generate_answer
        _set_llm(monkeypatch)

        async def fake_post(self, url, json=None, headers=None):
            return _Resp(jsonlib.dumps({"answer": "答。", "confidence": 0.5,
                                     "citations": [], "refusal_reason": ""}))

        monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
        out = await generate_answer("Q", [])
        assert out["refusal_reason"] is None
