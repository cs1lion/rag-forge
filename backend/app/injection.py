"""提示词注入识别与过滤（入库解析阶段第一道防线，配合 qa.py 随机 Nonce XML 边界形成纵深防御）。

P0 升级：
1. 保留与 `知识库_文本版/manifest.json` 同源的中文关键词与 9 条中文正则（100% 向后兼容）；
2. 新增 NFKC + 零宽字符清洗归一化，防御全角字符、零宽插字等混淆绕过；
3. 补齐英文 OWASP LLM01 越权/角色劫持/提示词套取/标签逃逸正则，并支持中英文句子切分；
4. 新增疑似 Base64 编码注入载荷解码检测。
"""
from __future__ import annotations

import base64
import re
import unicodedata

# 与 manifest.json flags.prompt_injection_keywords 同源（实测 4 篇 docx 首段命中）
INJECTION_KEYWORDS: list[str] = [
    "忽略所有",
    "提示词约束",
    "系统最高提示词",
    "必须强制遵循",
    "返回不知道",
    "不允许输出其他",
    "法律责任",
]

# 通用越权指令模式（中英双语 + 标签逃逸；不针对具体文档/句子写死）
INJECTION_PATTERNS: list[re.Pattern] = [
    # 中文注入模式
    re.compile(r"忽略(?:所有|之前|以上|上面|前面).{0,12}?(?:提示词|指令|约束|规则)"),
    re.compile(r"(?:忽略|无视).{0,8}?(?:系统|平台).{0,6}?(?:提示词|指令|约束)"),
    re.compile(r"只(?:能|得|需)?输出.{0,8}?(?:一句话|对不起|不知道|拒答)"),
    re.compile(r"(?:最高|最高级|平台级).{0,6}?(?:提示词|指令|约束)"),
    re.compile(r"(?:必须|务必)强制(?:遵循|执行).{0,6}?(?:提示词|指令|约束)"),
    re.compile(r"停止(?:解析|回答|输出).{0,10}?(?:返回|输出).{0,6}?不知道"),
    re.compile(r"(?:否则|不然).{0,10}?(?:承担|追究|付).{0,6}?法律责任"),
    re.compile(r"如果你是\s*(?:AI|人工智能|大模型|模型).{0,12}?(?:解析|阅读|处理|回答)"),
    re.compile(r"(?:必须|务必)遵循本(?:提示词|指令|约束)"),
    # 英文 OWASP LLM01 注入模式
    re.compile(
        r"\b(?:ignore|disregard|forget|override|bypass)\s+(?:all\s+)?"
        r"(?:previous|prior|above|earlier|system)\s+"
        r"(?:instructions?|prompts?|rules?|constraints?|directions?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:reveal|print|output|show|leak|dump)\s+(?:your\s+|the\s+)?"
        r"(?:system\s+prompt|hidden\s+instructions?|developer\s+prompt)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:you\s+are\s+now|act\s+as|pretend\s+to\s+be|switch\s+to)\s+"
        r"(?:an?\s+)?(?:unrestricted|jailbroken|dan|developer\s+mode)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:only\s+output|must\s+reply|respond\s+only\s+with)\b.{0,24}"
        r"\b(?:i\s+don'?t\s+know|sorry|refuse|cannot\s+answer)\b",
        re.IGNORECASE,
    ),
    # 边界标签逃逸尝试
    re.compile(
        r"</?\s*(?:retrieved_documents|retrieved_evidence_[a-f0-9]+|system|instructions)\s*>",
        re.IGNORECASE,
    ),
]

# 入库文档的风险提示文案（触发过滤时写入 documents.risk_warning）
RISK_WARNING_MESSAGE = "检测到疑似提示词注入指令，已在解析阶段自动过滤"

# 中英文句子切分：保留句末标点，且不误切小数点 (18.5%) 或文件名 (policy.md)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。；;!！？?\n])|(?<=\.)(?=\s|$)")

# 零宽/不可见混淆字符
_INVISIBLE_RE = re.compile(r"[\u200b\u200c\u200d\u2060\ufeff\u00ad]")

# 疑似 Base64 编码段（至少 24 字符，4 的倍数或带 = 补齐）
_BASE64_CANDIDATE_RE = re.compile(r"(?<![A-Za-z0-9+/=])[A-Za-z0-9+/]{24,}={0,2}(?![A-Za-z0-9+/=])")


def _normalize_for_scan(text: str) -> str:
    """NFKC 归一化 + 剥离零宽字符，抵御全角/零宽插字混淆。"""
    cleaned = _INVISIBLE_RE.sub("", text)
    return unicodedata.normalize("NFKC", cleaned)


def _scan_direct(norm_text: str) -> list[str]:
    hits: list[str] = [kw for kw in INJECTION_KEYWORDS if kw in norm_text]
    for pat in INJECTION_PATTERNS:
        for m in pat.finditer(norm_text):
            frag = m.group(0)
            if frag and frag not in hits:
                hits.append(frag)
    return hits


def _scan_base64_payloads(norm_text: str) -> list[str]:
    hits: list[str] = []
    for m in _BASE64_CANDIDATE_RE.finditer(norm_text):
        token = m.group(0)
        if len(token) % 4 != 0:
            continue
        try:
            decoded = base64.b64decode(token, validate=True).decode("utf-8")
        except Exception:
            continue
        sub_hits = _scan_direct(_normalize_for_scan(decoded))
        for sh in sub_hits:
            tag = f"base64:{sh}"
            if tag not in hits:
                hits.append(tag)
    return hits


def scan_injection(text: str) -> list[str]:
    """扫描文本，返回命中的注入特征（关键词原文 + 正则片段 + Base64 解码命中；空列表 = 未命中）。"""
    if not text:
        return []
    norm = _normalize_for_scan(text)
    hits = _scan_direct(norm)
    for b64_hit in _scan_base64_payloads(norm):
        if b64_hit not in hits:
            hits.append(b64_hit)
    return hits


def strip_injection(text: str) -> tuple[str, list[str], list[str]]:
    """从段落文本中剥离注入句子。

    返回 (clean_text, removed_sentences, hits)：
    - clean_text：移除注入句子后的剩余文本（可能为空串 → 整段丢弃）；
    - removed_sentences：被剥离的原句（隔离存档、可溯源）；
    - hits：命中的特征集合（用于审计）。
    """
    if not text:
        return "", [], []
    kept: list[str] = []
    removed: list[str] = []
    all_hits: list[str] = []
    for sent in _SENTENCE_SPLIT_RE.split(text):
        if not sent:
            continue
        hits = scan_injection(sent)
        if hits:
            removed.append(sent.strip())
            for h in hits:
                if h not in all_hits:
                    all_hits.append(h)
        else:
            kept.append(sent)
    clean = "".join(kept).strip()
    return clean, removed, all_hits
