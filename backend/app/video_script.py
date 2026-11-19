"""问答视频分镜脚本（固定三页结构）。

把问答（question + answer + citations）提炼为三页分镜：
  Page 1 · 问题检索   —— 问题全文 + 知识库来源提示
  Page 2 · 核心解答   —— 问题回顾 + 核心结论 + 至多 3 条要点
  Page 3 · 引用参考   —— 逐条文档卡片（文件名 / 章节路径 / 原文摘录）

每页携带独立 narration（逐页 TTS 的输入），渲染端按每页语音的真实时长切页，
实现严格音画同步（见 video.py）。

LLM 负责提炼第 2 页的「结论 + 要点 + 念白」；LLM 失败 / Schema 不满足时
降级为规则切句（仍使用真实 answer 文本，绝不 Mock）。
"""
from __future__ import annotations

import json
import re

from .config import settings

# 单页文本上限：保证在 1280×720 画布、88% 文本宽度下可完整折行不被裁切
SUMMARY_LIMIT = 60
POINT_LIMIT = 58
SNIPPET_LIMIT = 72
MAX_POINTS = 3
MAX_CITATIONS = 3

SCRIPT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "points": {"type": "array", "items": {"type": "string"}, "maxItems": MAX_POINTS},
        "narration": {"type": "string"},
    },
    "required": ["summary", "points", "narration"],
}


def _clip(text: str, limit: int) -> str:
    """按字符上限截断（中文按字计），保留完整句读可读性。"""
    t = (text or "").strip()
    if len(t) <= limit:
        return t
    return t[: limit - 1].rstrip("，。；、： ") + "…"


def _strip_end(text: str) -> str:
    return (text or "").strip().rstrip("。；！？.!?; ")


def _tidy_end(text: str) -> str:
    """降级切句可能在逗号/顿号处断开：展示与念白统一以省略号收尾。"""
    return re.sub(r"[，；、：]+$", "…", (text or "").strip())


# ---------------------------------------------------------------- 第 1 / 3 页

def _question_page(question: str, citations: list[dict]) -> dict:
    n = len(citations)
    meta = (
        f"知识库检索 · {n} 个来源段落 · 回答均可溯源"
        if n
        else "知识库检索 · 本次无匹配来源段落"
    )
    return {
        "kind": "question",
        "label": "问题检索",
        "title": question.strip(),
        "meta": meta,
        "narration": f"问题是：{_strip_end(question)}。",
    }


def _citations_page(citations: list[dict]) -> dict:
    cards = []
    for c in citations[:MAX_CITATIONS]:
        cards.append(
            {
                "source_file": str(c.get("source_file") or c.get("doc_id") or "未知文档"),
                "heading_path": str(c.get("heading_path") or ""),
                "snippet": _clip(str(c.get("snippet") or ""), SNIPPET_LIMIT),
            }
        )
    n = len(cards)
    narration = (
        f"以上回答参考了 {n} 份知识库文档，每段结论都可以在原文中溯源核对。"
        if n
        else "本次回答没有引用知识库文档。"
    )
    return {
        "kind": "citations",
        "label": "引用参考文档",
        "citations": cards,
        "narration": narration,
    }


# ---------------------------------------------------------------- 第 2 页

def _answer_page(summary: str, points: list[str], question: str, narration: str) -> dict:
    return {
        "kind": "answer",
        "label": "核心解答",
        "recap": question.strip(),
        "summary": summary,
        "points": points,
        "narration": narration,
    }


def _compose_narration(summary: str, points: list[str]) -> str:
    """把结论与要点串成自然念白（驱动第 2 页页面时长）。"""
    text = f"核心结论：{_strip_end(summary)}。"
    for i, p in enumerate(points, start=1):
        text += f"要点{i}：{_strip_end(p)}。"
    return text


def _split_sentences(text: str) -> list[str]:
    """答案切句（降级路径）：按句号/分号/问号/感叹号切，过长按逗号再切。"""
    parts = re.split(r"(?<=[。！？；])\s*", (text or "").strip())
    parts = [p for p in parts if p.strip()]
    if not parts:
        return [(text or "").strip() or "（无内容）"]
    out = []
    for p in parts:
        while len(p) > POINT_LIMIT:
            cut = p.find("，", 20, POINT_LIMIT)
            if cut == -1:
                cut = POINT_LIMIT - 1
            out.append(p[: cut + 1])
            p = p[cut + 1:]
        if p:
            out.append(p)
    return out


def _fallback_script(question: str, answer: str, citations: list[dict]) -> list[dict]:
    """规则降级：题卡 + 结论与要点 + 引用页（全部取自真实 answer）。"""
    sents = _split_sentences(answer)
    summary = _tidy_end(_clip(sents[0] if sents else "知识库未覆盖该问题。", SUMMARY_LIMIT))
    points = [_tidy_end(_clip(s, POINT_LIMIT)) for s in sents[1 : 1 + MAX_POINTS]]
    return [
        _question_page(question, citations),
        _answer_page(summary, points, question, _compose_narration(summary, points)),
        _citations_page(citations),
    ]


# ---------------------------------------------------------------- LLM 路径

def build_script_prompt(question: str, answer: str, citations: list[dict]) -> str:
    """组装分镜提示词（仅含真实问答与引用，不含注入语料指令）。"""
    cite_lines = []
    for c in citations[:MAX_CITATIONS]:
        cite_lines.append(
            f"- {c.get('source_file', c.get('doc_id', ''))} · "
            f"{c.get('heading_path', '')} · {c.get('para_id', '')}"
        )
    cite_block = "\n".join(cite_lines) if cite_lines else "- （无引用）"
    return (
        "你是问答视频的分镜导演。请把下面这段问答提炼为「核心解答页」的内容，输出严格 JSON：\n"
        f"1) summary：一句话核心结论，不超过 {SUMMARY_LIMIT} 字，措辞忠实于回答原文；\n"
        f"2) points：2 到 {MAX_POINTS} 条要点，每条不超过 {POINT_LIMIT} 字，"
        "逐字取自回答中的事实，可包含数字；\n"
        "3) narration：第 2 页的配音念白，把结论与要点连读成自然口语（总长 40-120 字）。\n"
        "不得编造回答中没有的信息。只输出 JSON，不要任何解释。\n\n"
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
                    'JSON 结构：{"summary":"...","points":["..."],"narration":"..."}'
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


def _validate_script(data: dict) -> dict | None:
    """校验 LLM 输出（summary/points/narration）；不满足返回 None。"""
    if not isinstance(data, dict):
        return None
    summary = data.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        return None
    raw_points = data.get("points", [])
    if not isinstance(raw_points, list) or any(not isinstance(p, str) for p in raw_points):
        return None
    points = [_clip(p, POINT_LIMIT) for p in raw_points if p.strip()][:MAX_POINTS]
    narration = data.get("narration")
    if not isinstance(narration, str) or not narration.strip():
        narration = _compose_narration(_clip(summary, SUMMARY_LIMIT), points)
    return {
        "summary": _clip(summary, SUMMARY_LIMIT),
        "points": points,
        "narration": narration.strip(),
    }


async def build_video_script(
    question: str, answer: str, citations: list[dict]
) -> tuple[list[dict], str]:
    """生成三页分镜。返回 (pages, method)：method 为 'llm' 或 'rule'。

    LLM 路径失败（调用异常 / JSON 非法 / Schema 不满足）→ 规则降级。
    """
    if not settings.llm_api_key or not settings.llm_base_url or not settings.llm_model:
        return _fallback_script(question, answer, citations), "rule"
    try:
        prompt = build_script_prompt(question, answer, citations)
        raw = await _call_llm(prompt)
        payload = _validate_script(json.loads(raw))
        if payload:
            pages = [
                _question_page(question, citations),
                _answer_page(
                    payload["summary"], payload["points"], question, payload["narration"]
                ),
                _citations_page(citations),
            ]
            return pages, "llm"
    except Exception:
        pass
    return _fallback_script(question, answer, citations), "rule"
