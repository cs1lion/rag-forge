"""P3 问答 SSE Token 级流式输出封装。

复用 P0 的随机 Nonce XML 隔离边界与 P2 的声明级忠实度验真，按标准 SSE 事件流依次推送：
1. event: retrieval  -> 命中的证据段落及 score_breakdown (fts / vector / rrf)
2. event: token      -> LLM 增量文本片段
3. event: verified   -> 最终答案、引用四件套、verification 忠实度报告或安全拒答
4. event: done       -> 流结束信号
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator

from .config import settings
from .faithfulness import verify_answer_faithfulness
from .qa import _detect_output_compromise, build_guarded_prompt


def format_sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def stream_guarded_answer(
    question: str, citations: list[dict]
) -> AsyncIterator[str]:
    """流式调用 OpenAI 兼容 /chat/completions 接口，边吐字边保留防注入与验真护栏。"""
    import httpx

    yield format_sse("retrieval", {"citations": citations})

    if not citations:
        yield format_sse(
            "verified",
            {
                "answer": "知识库未覆盖该问题。",
                "refusal_reason": "E_NO_EVIDENCE",
                "confidence": 0.0,
                "citations": [],
                "verification": verify_answer_faithfulness("", []),
            },
        )
        yield format_sse("done", {"ok": True})
        return

    system_prompt, user_content, nonce = build_guarded_prompt(question, citations)
    # 流式模式直接输出自然语言正文，避免前端等待整个 JSON 闭合造成高首字延迟
    stream_system = (
        system_prompt
        + "\n\n流式输出模式：请直接输出清晰、精炼的中文答案正文（不要外包 JSON 或 Markdown 代码块）。"
    )
    payload = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": stream_system},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.2,
        "max_tokens": settings.llm_max_tokens,
        "stream": True,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.llm_api_key}",
    }

    chunks: list[str] = []
    async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
        async with client.stream(
            "POST",
            f"{settings.llm_base_url}/chat/completions",
            json=payload,
            headers=headers,
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                body = line[5:].strip()
                if body == "[DONE]":
                    break
                try:
                    evt = json.loads(body)
                    delta = evt["choices"][0].get("delta", {}).get("content") or ""
                except Exception:
                    continue
                if delta:
                    chunks.append(delta)
                    yield format_sse("token", {"delta": delta})

    full_answer = "".join(chunks).strip()
    if _detect_output_compromise(full_answer, nonce):
        yield format_sse(
            "verified",
            {
                "answer": "检测到异常输出边界泄露，已触发安全保护拦截。",
                "refusal_reason": "E_PROMPT_LEAK_GUARD",
                "confidence": 0.0,
                "citations": [],
                "verification": verify_answer_faithfulness("", []),
            },
        )
    else:
        verification = verify_answer_faithfulness(full_answer, citations)
        yield format_sse(
            "verified",
            {
                "answer": full_answer,
                "refusal_reason": None,
                "confidence": verification["faithfulness_score"],
                "citations": citations[:5],
                "verification": verification,
            },
        )
    yield format_sse("done", {"ok": True})
