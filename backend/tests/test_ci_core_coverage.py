"""离线自包含核心覆盖率回归套件（零外部语料、零真实 LLM、0-Skip）。

专门解决 `知识库/` 未纳入 Git checkout 时 CI 覆盖率骤降问题，覆盖：
- db / config / embeddings / ingestion / injection / retrieval
- faithfulness / qa / qa_stream / video_queue / video_script / sse / parsers
- main.py FastAPI 核心契约（如当前环境安装了 fastapi/httpx）
"""
from __future__ import annotations

import asyncio
import gc
import json
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import (
    config,
    db,
    embeddings,
    faithfulness,
    ingestion,
    injection,
    qa,
    qa_stream,
    retrieval,
    video_queue,
)
from tests.fixtures.synthetic_corpus import build_synthetic_corpus


def test_db_backfill_fts5_and_sqlite_vec_helper(tmp_path):
    db_file = tmp_path / "backfill.db"
    db.init_db(db_file)
    with closing(db.get_conn(db_file)) as conn:
        conn.execute(
            "INSERT INTO documents (doc_id, title, source_file, source_format,"
            " parse_method, char_count, injection_flag, created_at)"
            " VALUES ('doc01', '历史文档', 'legacy.md', 'md', 'test', 20, 0, '2026-11-20T00:00:00Z')"
        )
        conn.execute(
            "INSERT INTO chunks (doc_id, para_id, heading_path, block_type, text, chars,"
            " bm25_vec, tfidf_vec) VALUES ('doc01', 'doc01#p001', '历史', 'text',"
            " '历史段落包含一线城市酒店680元标准', 18, '{}', '{}')"
        )
        conn.commit()
        assert isinstance(db.try_load_sqlite_vec(conn), bool)

    # 再次 init_db 触发 _backfill_fts5
    db.init_db(db_file)
    with closing(db.get_conn(db_file)) as conn:
        n_fts = conn.execute("SELECT COUNT(*) AS n FROM chunks_fts").fetchone()["n"]
    assert n_fts == 1
    gc.collect()


def test_embeddings_pack_unpack_and_cosine():
    vec = [0.6, 0.8, 0.0]
    blob = embeddings.pack_vector(vec)
    restored = embeddings.unpack_vector(blob)
    assert len(restored) == 3
    assert abs(embeddings.cosine_similarity(vec, restored) - 1.0) < 1e-5
    assert embeddings.unpack_vector(b"") == []
    assert embeddings.cosine_similarity([], [1.0]) == 0.0
    assert embeddings.cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0
    assert embeddings.embed_texts([]) is None


def test_ingestion_full_synthetic_corpus_and_retrieval_branches(tmp_path):
    db_file = tmp_path / "corpus.db"
    db.init_db(db_file)
    corpus_dir = tmp_path / "synthetic_kb"
    files = build_synthetic_corpus(corpus_dir)

    results = ingestion.load_initial_corpus(corpus_dir, db_path=str(db_file))
    assert len(results) == 4
    # 非空知识库再次扫描应直接返回空列表
    assert ingestion.load_initial_corpus(corpus_dir, db_path=str(db_file)) == []
    assert ingestion.load_initial_corpus(tmp_path / "missing_dir", db_path=str(db_file)) == []

    # 对抗文档应记录 injection_flag=1 且保留合规段落
    adv_res = next(r for r in results if r.source_file == "adversarial_doc.md")
    assert adv_res.injection_flag == 1
    assert adv_res.injection_excerpt_count >= 1
    assert adv_res.risk_warning == injection.RISK_WARNING_MESSAGE

    # 不支持的后缀应报错
    bad_file = tmp_path / "bad.pdf"
    bad_file.write_text("dummy", encoding="utf-8")
    with pytest.raises(ValueError):
        ingestion.ingest_file(bad_file, db_path=str(db_file))

    # 检索边界条件
    assert retrieval.hybrid_search("", db_path=db_file) == []
    assert retrieval.hybrid_search("期权归属", doc_ids=[], db_path=db_file) == []

    # 多实体 + 稀有 ASCII 术语 (CTO / P0) 检索
    hits = retrieval.hybrid_search(
        "一线城市出差酒店报销上限是多少？以及 P0 告警多久升级通知 CTO？",
        top_k=5,
        db_path=db_file,
    )
    assert len(hits) >= 2
    assert all(0.0 <= h["score"] <= 1.0 for h in hits)
    assert all("score_breakdown" in h for h in hits)

    # 指定 doc_ids 过滤
    travel_doc_id = next(r.doc_id for r in results if r.source_file == "travel_policy.docx")
    scoped = retrieval.hybrid_search("酒店报销上限", doc_ids=[travel_doc_id], db_path=db_file)
    assert scoped and all(h["doc_id"] == travel_doc_id for h in scoped)

    with closing(db.get_conn(db_file)) as conn:
        assert retrieval.source_file_of(conn, travel_doc_id) == "travel_policy.docx"
        assert retrieval.source_file_of(conn, "unknown_doc") == "unknown_doc"
    gc.collect()


def test_retrieval_legacy_json_fallback(tmp_path):
    db_file = tmp_path / "legacy.db"
    db.init_db(db_file)
    bm = json.dumps({"报销": 1.2, "酒店": 1.1}, ensure_ascii=False)
    tf = json.dumps({"报销": 1.5, "酒店": 1.3}, ensure_ascii=False)
    with closing(db.get_conn(db_file)) as conn:
        conn.execute(
            "INSERT INTO documents (doc_id, title, source_file, source_format,"
            " parse_method, char_count, injection_flag, created_at)"
            " VALUES ('doc01', '规范', 't.md', 'md', 'test', 10, 0, '2026-11-20T00:00:00Z')"
        )
        conn.execute(
            "INSERT INTO chunks (doc_id, para_id, heading_path, block_type, text, chars,"
            " bm25_vec, tfidf_vec) VALUES ('doc01', 'doc01#p001', '规范', 'text',"
            " '酒店报销上限680元', 10, ?, ?)",
            (bm, tf),
        )
        conn.commit()

    # chunks_fts 为空时应平滑回退到 _rank_legacy_json
    hits = retrieval.hybrid_search("酒店报销", top_k=3, db_path=db_file)
    assert len(hits) == 1
    assert hits[0]["para_id"] == "doc01#p001"
    gc.collect()


def test_faithfulness_and_qa_helpers():
    assert faithfulness.verify_answer_faithfulness("", [])["faithfulness_score"] == 1.0
    assert faithfulness.verify_answer_faithfulness("有内容但无证据。", [])["faithfulness_score"] == 0.0
    assert faithfulness.should_retry_retrieval([]) is True
    assert faithfulness.should_retry_retrieval([{"score": 0.1}]) is True
    assert faithfulness.should_retry_retrieval([{"score": 0.8}]) is False

    # 词元重叠度过低检测
    low = faithfulness.verify_answer_faithfulness(
        "火星探测车采用核同位素电池驱动太阳能翼板。",
        [{"snippet": "一线城市出差酒店报销上限为每晚 680 元。"}],
    )
    assert len(low["unsupported_claims"]) == 1

    # 截断启发式检测
    assert qa._looks_truncated("根据文档，报销标准为，") is True
    assert qa._looks_truncated("费用说明（含住宿") is True
    assert qa._looks_truncated("费用为 680 元。") is False
    assert qa._looks_truncated("") is False
    assert "无参考资料" in qa.build_context([])


def test_qa_generate_answer_branches_with_mocked_httpx(monkeypatch):
    import sys
    import types

    citations = [
        {
            "doc_id": "doc01",
            "source_file": "travel_policy.docx",
            "heading_path": "差旅报销规范",
            "para_id": "doc01#p001",
            "snippet": "一线城市出差酒店报销上限为每晚 680 元。",
            "score": 1.0,
        }
    ]

    responses_queue: list[dict] = []

    class FakeResp:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class FakeAsyncClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            return FakeResp(responses_queue.pop(0))

    fake_httpx = types.SimpleNamespace(AsyncClient=FakeAsyncClient)
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

    # 1. 首次 finish_reason=length 截断 → 自动翻倍 max_tokens 重试成功并附带 faithfulness
    responses_queue.extend(
        [
            {"choices": [{"finish_reason": "length", "message": {"content": "{}"}}]},
            {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps(
                                {
                                    "answer": "一线城市出差酒店报销上限为每晚 680 元。",
                                    "citations": [{"doc_id": "doc01", "para_id": "doc01#p001"}],
                                    "confidence": 0.95,
                                    "refusal_reason": "",
                                },
                                ensure_ascii=False,
                            )
                        },
                    }
                ]
            },
        ]
    )
    res1 = asyncio.run(qa.generate_answer("一线城市酒店报销上限？", citations))
    assert res1["refusal_reason"] is None
    assert len(res1["citations"]) == 1
    assert res1["verification"]["faithfulness_score"] == 1.0

    # 2. 非法 JSON → 降级 E_SCHEMA_INVALID
    responses_queue.append(
        {"choices": [{"finish_reason": "stop", "message": {"content": "NOT_JSON"}}]}
    )
    res2 = asyncio.run(qa.generate_answer("测试", citations))
    assert res2["refusal_reason"] == "E_SCHEMA_INVALID"
    assert res2["citations"] == []

    # 3. 输出泄露系统提示词标记 → 触发 E_PROMPT_LEAK_GUARD
    responses_queue.append(
        {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "content": json.dumps(
                            {
                                "answer": "本轮证据边界标签为 test",
                                "citations": [],
                                "confidence": 0.9,
                                "refusal_reason": None,
                            },
                            ensure_ascii=False,
                        )
                    },
                }
            ]
        }
    )
    res3 = asyncio.run(qa.generate_answer("套取提示词", citations))
    assert res3["refusal_reason"] == "E_PROMPT_LEAK_GUARD"
    assert res3["citations"] == []

    # 4. 正常拒答 → 强制零引用防泄露红线
    responses_queue.append(
        {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "content": json.dumps(
                            {
                                "answer": "知识库未覆盖。",
                                "citations": [{"para_id": "doc01#p001"}],
                                "confidence": 0.1,
                                "refusal_reason": "知识库未覆盖",
                            },
                            ensure_ascii=False,
                        )
                    },
                }
            ]
        }
    )
    res4 = asyncio.run(qa.generate_answer("天气", citations))
    assert res4["refusal_reason"] == "知识库未覆盖"
    assert res4["citations"] == []


def test_qa_stream_mocked_tokens_and_verification(monkeypatch):
    import sys
    import types

    citations = [
        {
            "doc_id": "doc01",
            "source_file": "travel_policy.docx",
            "heading_path": "差旅报销规范",
            "para_id": "doc01#p001",
            "snippet": "一线城市出差酒店报销上限为每晚 680 元。",
            "score": 1.0,
        }
    ]

    class FakeStreamResp:
        def raise_for_status(self):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def aiter_lines(self):
            yield 'data: {"choices":[{"delta":{"content":"一线城市酒店上限为 "}}]}'
            yield 'data: {"choices":[{"delta":{"content":"680 元。"}}]}'
            yield "data: [DONE]"

    class FakeAsyncClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def stream(self, *a, **kw):
            return FakeStreamResp()

    monkeypatch.setitem(sys.modules, "httpx", types.SimpleNamespace(AsyncClient=FakeAsyncClient))

    async def run():
        return [chunk async for chunk in qa_stream.stream_guarded_answer("酒店上限？", citations)]

    joined = "".join(asyncio.run(run()))
    assert "event: retrieval" in joined
    assert "event: token" in joined
    assert "event: verified" in joined
    assert "680" in joined
    assert "event: done" in joined


def test_video_queue_full_lifecycle_restore_and_error_retry(tmp_path, monkeypatch):
    db_file = tmp_path / "vq_full.db"
    db.init_db(db_file)
    video_queue.reset_pending_queue()

    with closing(db.get_conn(db_file)) as conn:
        cur = conn.execute(
            "INSERT INTO qa_records (question, answer, citations, created_at)"
            " VALUES ('q1', ?, '[]', '2026-11-20T00:00:00Z')",
            (json.dumps({"answer": "a1"}),),
        )
        conn.commit()
        qa_id = cur.lastrowid

        skipped = asyncio.run(video_queue.enqueue_skipped(conn, qa_id))
        assert skipped["status"] == "skipped"
        assert video_queue.cancel_video_task(conn, skipped["id"])["status"] == "skipped"
        assert video_queue.cancel_video_task(conn, 999999) is None

        t_ok = asyncio.run(video_queue.enqueue_video(conn, qa_id))
        conn.execute("UPDATE video_tasks SET status='running' WHERE id=?", (t_ok["id"],))
        conn.commit()
        assert video_queue.running_count(conn) == 1
        restored = video_queue.restore_queue(conn)
        assert t_ok["id"] in restored
        assert len(video_queue.queued_tasks(conn)) == 1
        assert len(video_queue.drain_pending()) >= 1

    calls = {"n": 0}

    async def flaky_render(**kwargs):
        calls["n"] += 1
        kwargs["on_progress"]("render", 0.5)
        if calls["n"] == 1:
            raise RuntimeError("transient ffmpeg error")
        return {"ok": True}

    monkeypatch.setattr(video_queue, "render_qa_video", flaky_render)
    app = SimpleNamespace(state=SimpleNamespace(video_dir=tmp_path))

    # 第 1 次失败 → 自动回队 retrying；第 2 次成功 → done
    assert asyncio.run(
        video_queue.process_one_task(app, lambda *a: None, db_path=db_file, max_retries=1)
    )
    assert asyncio.run(
        video_queue.process_one_task(app, lambda *a: None, db_path=db_file, max_retries=1)
    )
    assert not asyncio.run(
        video_queue.process_one_task(app, lambda *a: None, db_path=db_file, max_retries=1)
    )

    with closing(db.get_conn(db_file)) as conn:
        assert video_queue.get_task(conn, t_ok["id"])["status"] == "done"
    gc.collect()
