"""P2 声明级引用忠实度校验（Claim-Level Faithfulness Verifier）与低召回改写辅助。

解决传统 RAG 只验证 para_id 存在、却无法识别"编造数字/结论但挂真实 para_id"的盲区：
- 零外部 LLM 成本的确定性 L1 验真：将回答切分为声明句，校验关键数字与实体词元在
  已引用证据片段中的覆盖率；
- 输出结构化 `verification` 字段（faithfulness_score / verified_claims / unsupported_claims），
  与既有 ANSWER_SCHEMA 完全兼容。
"""
from __future__ import annotations

import re

_CLAIM_SPLIT_RE = re.compile(r"(?<=[。；;!！？?\n])|(?<=\.)(?=\s|$)")
_NUM_RE = re.compile(r"\d+(?:\.\d+)?%?")
_TOKEN_RE = re.compile(r"[一-龥]{2,}|[a-zA-Z0-9]{2,}")

# 常规礼貌/过渡/拒答短句不计入事实幻觉
_META_PHRASES = (
    "根据文档",
    "文档未给出",
    "文档未提供",
    "知识库未覆盖",
    "综上所述",
    "总结如下",
    "参考资料",
)


def _extract_bigrams(text: str) -> set[str]:
    out: set[str] = set()
    for m in _TOKEN_RE.finditer(text or ""):
        s = m.group()
        if re.match(r"^[一-龥]+$", s):
            if len(s) <= 2:
                out.add(s)
            else:
                for i in range(len(s) - 1):
                    out.add(s[i : i + 2])
        else:
            out.add(s.lower())
    return out


def verify_answer_faithfulness(answer: str, citations: list[dict]) -> dict:
    """确定性声明级验真：校验回答中的数字与核心词元是否被引用证据支撑。"""
    text = (answer or "").strip()
    if not text or not citations:
        return {
            "faithfulness_score": 1.0 if not text else 0.0,
            "total_claims": 0,
            "supported_claims": 0,
            "unsupported_claims": [],
        }

    evidence_text = "\n".join(
        str(c.get("snippet") or c.get("text") or "") for c in citations
    )
    ev_tokens = _extract_bigrams(evidence_text)
    ev_numbers = set(_NUM_RE.findall(evidence_text))

    claims = [s.strip() for s in _CLAIM_SPLIT_RE.split(text) if len(s.strip()) >= 6]
    if not claims:
        return {
            "faithfulness_score": 1.0,
            "total_claims": 0,
            "supported_claims": 0,
            "unsupported_claims": [],
        }

    supported = 0
    unsupported: list[dict] = []
    for claim in claims:
        if any(p in claim for p in _META_PHRASES) and not _NUM_RE.search(claim):
            supported += 1
            continue
        claim_nums = set(_NUM_RE.findall(claim))
        missing_nums = sorted(claim_nums - ev_numbers)
        c_toks = _extract_bigrams(claim)
        overlap = (len(c_toks & ev_tokens) / max(len(c_toks), 1)) if c_toks else 1.0

        if missing_nums:
            unsupported.append(
                {
                    "claim": claim,
                    "reason": f"未在引用证据中出现的数值: {', '.join(missing_nums)}",
                    "overlap": round(overlap, 3),
                }
            )
        elif overlap < 0.2:
            unsupported.append(
                {
                    "claim": claim,
                    "reason": "与引用证据语义/词元重叠度过低",
                    "overlap": round(overlap, 3),
                }
            )
        else:
            supported += 1

    total = len(claims)
    score = round(supported / total, 4) if total else 1.0
    return {
        "faithfulness_score": score,
        "total_claims": total,
        "supported_claims": supported,
        "unsupported_claims": unsupported,
    }


def should_retry_retrieval(citations: list[dict], *, min_top_score: float = 0.25) -> bool:
    """当检索为空或最高相关性过低时，触发单轮查询改写重检。"""
    if not citations:
        return True
    top_score = max(float(c.get("score") or 0.0) for c in citations)
    return top_score < min_top_score
