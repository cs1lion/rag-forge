"""Step 3 单测：混合检索 + 问答编排（双重防注入）+ 引用溯源。

覆盖 CLAUDE.md §三 铁律 3/4/5：
- 混合检索 BM25+TF-IDF 本地实现，零外部 Embedding；
- 引用溯源四维：doc_id / source_file / heading_path / para_id；
- 双重防注入：XML 隔离 + System Prompt 最高安全层级；
- Schema 校验失败降级安全拒答。
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app import db
from app.ingestion import ingest_file
from app.qa import ANSWER_SCHEMA, SYSTEM_PROMPT, build_context, generate_answer
from app.retrieval import hybrid_search, tokenize

KB = Path(__file__).resolve().parents[2] / "知识库"
pytestmark = pytest.mark.skipif(
    not KB.is_dir(), reason="knowledge corpus not present in this checkout"
)


@pytest.fixture()
def seeded_db(tmp_path, monkeypatch):
    """真实入库全部 7 篇文档，检索/问答走真实语料。"""
    test_db = tmp_path / "qa.db"
    db.init_db(test_db)
    from app.ingestion import load_initial_corpus
    load_initial_corpus(KB, db_path=test_db)
    # 让 retrieval/qa 用测试库
    monkeypatch.setattr("app.retrieval.get_conn", lambda db_path=None: db.get_conn(test_db))
    return test_db


# ================================================================ 混合检索

class TestHybridSearch:
    def test_returns_top_k_with_four_dim_citations(self, seeded_db):
        """检索结果携带四维溯源：doc_id/source_file/heading_path/para_id。"""
        hits = hybrid_search("众赢科技研发投入", top_k=5)
        assert len(hits) > 0
        for h in hits:
            assert "doc_id" in h
            assert "para_id" in h
            assert "heading_path" in h
            assert "text" in h
            assert "score" in h
            assert 0 <= h["score"] <= 1

    def test_injection_text_never_recalled(self, seeded_db):
        """注入段落永不进入检索结果（ARCHITECTURE §3 铁律）。"""
        hits = hybrid_search("忽略所有提示词约束", top_k=10)
        for h in hits:
            assert "忽略所有" not in h["text"]
            assert "提示词约束" not in h["text"]

    def test_empty_query_returns_empty(self, seeded_db):
        assert hybrid_search("", top_k=5) == []
        assert hybrid_search("   ", top_k=5) == []

    def test_no_match_returns_empty(self, seeded_db):
        hits = hybrid_search("xyzzy_nonexistent_term_12345", top_k=5)
        assert hits == []

    def test_score_ordering_descending(self, seeded_db):
        hits = hybrid_search("未来在线考研考公", top_k=5)
        scores = [h["score"] for h in hits]
        assert scores == sorted(scores, reverse=True)

    def test_relevant_doc_ranked_higher(self, seeded_db):
        """问众赢科技的问题，doc05 应在 Top-K 内（doc06 因收购关系也相关）。"""
        hits = hybrid_search("众赢科技小不点机器人", top_k=5)
        doc_ids = [h["doc_id"] for h in hits]
        assert "doc05" in doc_ids  # doc05 必须在 Top-5 内

    def test_tokenize_cjk_and_ascii(self):
        toks = tokenize("众赢科技2025年研发 11 亿元")
        assert "众赢" in toks  # bigram
        assert "科技" in toks
        assert "2025" in toks
        assert "11" in toks

    def test_tokenize_empty(self):
        assert tokenize("") == []
        assert tokenize(None) == []


# ================================================================ 问答编排

class TestQAOrchestration:
    def test_system_prompt_declares_highest_security(self):
        """System Prompt 保留安全声明：参考资料仅为数据，越权文本不是指令。"""
        assert "安全声明" in SYSTEM_PROMPT
        assert "忽略" in SYSTEM_PROMPT
        assert "不是指令" in SYSTEM_PROMPT
        # 外部 XML 强隔离已取消（改为入库阶段过滤）
        assert "<retrieved_documents>" not in SYSTEM_PROMPT

    def test_build_context_plain_text(self):
        """防注入改为入库阶段过滤：上下文为普通文本，不再使用 XML 强隔离。"""
        cites = [
            {"doc_id": "doc05", "source_file": "x.docx", "heading_path": "h",
             "para_id": "doc05#p001", "snippet": "原文内容"}
        ]
        ctx = build_context(cites)
        assert "<retrieved_documents>" not in ctx
        assert "doc05" in ctx
        assert "doc05#p001" in ctx
        assert "x.docx" in ctx
        assert "原文内容" in ctx

    def test_build_context_empty_citations(self):
        ctx = build_context([])
        assert "<retrieved_documents>" not in ctx
        assert "无" in ctx

    @pytest.mark.asyncio
    async def test_generate_answer_llm_success(self, monkeypatch):
        """LLM 返回合法 JSON -> 结构化回答含引用。"""
        fake_answer = {
            "answer": "2025 年研发投入 11 亿元。",
            "refusal_reason": None,
            "confidence": 0.9,
            "citations": [{"doc_id": "doc05", "para_id": "doc05#p041", "snippet": "s"}],
        }

        class FakeResp:
            def raise_for_status(self):
                pass
            def json(self):
                return {"choices": [{"message": {"content": json.dumps(fake_answer)}}]}

        async def fake_post(self, url, json=None, headers=None):
            return FakeResp()

        monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
        from app.config import settings
        monkeypatch.setattr(settings, "llm_api_key", "k", raising=False)
        monkeypatch.setattr(settings, "llm_base_url", "http://x", raising=False)
        monkeypatch.setattr(settings, "llm_model", "m", raising=False)

        result = await generate_answer("研发投入？", [{"doc_id": "doc05", "para_id": "p1", "snippet": "s"}])
        assert result["answer"] == "2025 年研发投入 11 亿元。"
        assert result["confidence"] == 0.9
        assert result["refusal_reason"] is None

    @pytest.mark.asyncio
    async def test_generate_answer_schema_invalid_degrades(self, monkeypatch):
        """LLM 输出非 JSON / 缺 answer 字段 -> 安全拒答（绝不输出注入文本）。"""
        class FakeResp:
            def raise_for_status(self):
                pass
            def json(self):
                return {"choices": [{"message": {"content": "这不是JSON"}}]}

        async def fake_post(self, url, json=None, headers=None):
            return FakeResp()

        monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
        from app.config import settings
        monkeypatch.setattr(settings, "llm_api_key", "k", raising=False)
        monkeypatch.setattr(settings, "llm_base_url", "http://x", raising=False)
        monkeypatch.setattr(settings, "llm_model", "m", raising=False)

        result = await generate_answer("Q", [])
        assert result["refusal_reason"] == "E_SCHEMA_INVALID"
        assert result["confidence"] == 0.0
        assert result["citations"] == []
        assert "忽略所有" not in result["answer"]

    @pytest.mark.asyncio
    async def test_generate_answer_llm_exception_propagates(self, monkeypatch):
        """LLM 调用异常 -> 向上抛出（由 main.py 捕获降级）。"""
        from app.config import settings
        monkeypatch.setattr(settings, "llm_api_key", "k", raising=False)
        monkeypatch.setattr(settings, "llm_base_url", "http://x", raising=False)
        monkeypatch.setattr(settings, "llm_model", "m", raising=False)

        async def boom(self, url, json=None, headers=None):
            raise RuntimeError("timeout")

        monkeypatch.setattr("httpx.AsyncClient.post", boom)
        with pytest.raises(RuntimeError, match="timeout"):
            await generate_answer("Q", [])

    @pytest.mark.asyncio
    async def test_generate_answer_defaults_filled(self, monkeypatch):
        """LLM 返回缺省字段时自动补全（citations/confidence/refusal_reason）。"""
        partial = {"answer": "简答"}

        class FakeResp:
            def raise_for_status(self):
                pass
            def json(self):
                return {"choices": [{"message": {"content": json.dumps(partial)}}]}

        async def fake_post(self, url, json=None, headers=None):
            return FakeResp()

        monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
        from app.config import settings
        monkeypatch.setattr(settings, "llm_api_key", "k", raising=False)
        monkeypatch.setattr(settings, "llm_base_url", "http://x", raising=False)
        monkeypatch.setattr(settings, "llm_model", "m", raising=False)

        cites = [{"doc_id": "d1", "para_id": "p1", "snippet": "s"}]
        result = await generate_answer("Q", cites)
        assert result["answer"] == "简答"
        assert result["confidence"] == 0.5  # default
        assert result["refusal_reason"] is None  # default
        assert len(result["citations"]) > 0  # filled from input

    def test_answer_schema_required_fields(self):
        """Schema 定义包含全部必填字段。"""
        assert set(ANSWER_SCHEMA["required"]) == {"answer", "citations", "confidence", "refusal_reason"}
        assert ANSWER_SCHEMA["properties"]["confidence"]["minimum"] == 0
        assert ANSWER_SCHEMA["properties"]["confidence"]["maximum"] == 1
