"""大模型分镜脚本（CLAUDE.md 视频技术栈：大模型提炼结构化分镜脚本）。

把问答（question + answer + citations）提炼为结构化分镜段序列：
  - title    题卡（问题）
  - body     答案逐句（每句一段，≤60 字，利于字幕对齐）
  - citations 引用页（溯源四维：doc_id/source_file/heading_path/para_id）

输出强制 JSON Schema；LLM 失败 / Schema 不满足时降级为规则切句
（降级路径仍走真实 answer 文本，绝不 Mock）。
"""
from __future__ import annotations

import json
import re

from .config import settings

SCRIPT_SCHEMA = {
    "type": "object",
    "properties": {
        "segments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["title", "body", "citations"]},
                    "title": {"type": "string"},
                    "subtitle": {"type": "string"},
                    "narration": {"type": "string"},
                },
                "required": ["kind", "title", "narration"],
            },
            "minItems": 1,
        }
    },
    "required": ["segments"],
}


def build_script_prompt(question: str, answer: str, citations: list[dict]) -> str:
    """组装分镜提示词（仅含真实问答与引用，不含注入语料指令）。"""
    cite_lines = []
    for c in citations[:5]:
        cite_lines.append(
            f"- {c.get('source_file', c.get('doc_id', ''))} · "
            f"{c.get('heading_path', '')} · {c.get('para_id', '')}"
        )
    cite_block = "\n".join(cite_lines) if cite_lines else "- （无引用）"
    return (
        "你是问答视频的分镜导演。把下面这段问答拆成 3 类镜头段，输出严格 JSON：\n"
        "1) title 题卡：title=问题原文，narration=读出问题（可加“问题是”前缀）；\n"
        "2) body 答案：把 answer 按句拆成若干段，每段 title=narration=该句原文，"
        "单段不超过 60 字，措辞与 answer 逐字一致，不得改写、不得编造；\n"
        "3) citations 引用页：title=“引用参考”，subtitle=引用文档列表（每行一个，"
        "含文件名与标题路径），narration=“以上回答引用了 N 个知识库段落”。\n"
        "只输出 JSON，不要任何解释。\n\n"
        f"【问题】\n{question}\n\n【回答】\n{answer}\n\n【引用】\n{cite_block}"
    )


async def _call_llm(prompt: str) -> str:
    """调 LLM（OpenAI 兼容协议），返回原始文本；失败抛异常。"""
    import httpx

    payload = {
        "model": settings.llm_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你只输出合法 JSON，不输出任何解释文字。"
                    "JSON 结构：{\"segments\":[{\"kind\":\"title|body|citations\","
                    "\"title\":\"...\",\"subtitle\":\"...\",\"narration\":\"...\"}]}"
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": settings.llm_max_tokens,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.llm_api_key}",
    }
    async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
        r = await client.post(
            f"{settings.llm_base_url}/chat/completions", json=payload, headers=headers
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


def _split_sentences(text: str) -> list[str]:
    """答案切句（降级路径）：按句号/分号/问号/感叹号切，过长按逗号再切。"""
    parts = re.split(r"(?<=[。！？；])\s*", text.strip())
    parts = [p for p in parts if p]
    if not parts:
        return [text.strip() or "（无内容）"]
    out = []
    for p in parts:
        while len(p) > 60:
            cut = p.find("，", 30, 60)
            if cut == -1:
                cut = 60
            out.append(p[: cut + 1])
            p = p[cut + 1:]
        out.append(p)
    return out


def _fallback_script(question: str, answer: str, citations: list[dict]) -> list[dict]:
    """规则降级：无 LLM 时仍产出真实分镜（题卡 + 答案逐句 + 引用页）。"""
    segs = [
        {
            "kind": "title",
            "title": question,
            "subtitle": "知识库问答 · 引用溯源见片尾",
            "narration": f"问题是：{question}",
        }
    ]
    for s in _split_sentences(answer):
        segs.append({"kind": "body", "title": s, "subtitle": "", "narration": s})
    if citations:
        cite_lines = [
            f"{c.get('source_file', c.get('doc_id', ''))} · {c.get('heading_path', '')}"
            for c in citations[:5]
        ]
        segs.append(
            {
                "kind": "citations",
                "title": "引用参考",
                "subtitle": " · ".join(cite_lines) or "无",
                "narration": f"以上回答引用了 {len(citations)} 个知识库段落。",
            }
        )
    return segs


def _validate_script(data: dict) -> list[dict] | None:
    """校验 LLM 输出满足分镜 Schema；不满足返回 None。"""
    if not isinstance(data, dict):
        return None
    segs = data.get("segments")
    if not isinstance(segs, list) or not segs:
        return None
    out = []
    for s in segs:
        if not isinstance(s, dict):
            return None
        kind = s.get("kind")
        if kind not in ("title", "body", "citations"):
            return None
        title = s.get("title")
        narration = s.get("narration")
        if not isinstance(title, str) or not isinstance(narration, str):
            return None
        out.append(
            {
                "kind": kind,
                "title": title,
                "subtitle": str(s.get("subtitle", "")),
                "narration": narration,
            }
        )
    return out


async def build_video_script(
    question: str, answer: str, citations: list[dict]
) -> tuple[list[dict], str]:
    """生成分镜脚本。返回 (segments, method)：method 为 'llm' 或 'rule'。

    LLM 路径失败（调用异常 / JSON 非法 / Schema 不满足）→ 规则降级。
    """
    if not settings.llm_api_key or not settings.llm_base_url or not settings.llm_model:
        return _fallback_script(question, answer, citations), "rule"
    try:
        prompt = build_script_prompt(question, answer, citations)
        raw = await _call_llm(prompt)
        data = json.loads(raw)
        segs = _validate_script(data)
        if segs:
            return segs, "llm"
    except Exception:
        pass
    return _fallback_script(question, answer, citations), "rule"
