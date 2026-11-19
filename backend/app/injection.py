"""提示词注入识别与过滤（入库解析阶段执行）。

设计变更（本次需求）：取消问答侧的外部 XML 强制隔离，改为在**入库解析阶段**
自动识别典型提示词注入模式并从切块文本中剥离过滤，同时在文档上记录
`risk_warning` 风险提示，问答返回时汇总涉及文档的风险提示。

识别两类信号：
1. 与 `知识库_文本版/manifest.json` 的 `flags.prompt_injection_keywords` 同源的
   特征词（保持原有实测口径）；
2. 通用越权指令模式（正则）：忽略前文/提示词约束、只输出一句话、
   最高提示词约束、强制遵循、拒答指令等。均为通用模式，不针对具体句子写死。
"""
from __future__ import annotations

import re

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

# 通用越权指令模式（不针对具体文档/句子写死；命中即视为注入片段）
INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"忽略(?:所有|之前|以上|上面|前面).{0,12}?(?:提示词|指令|约束|规则)"),
    re.compile(r"(?:忽略|无视).{0,8}?(?:系统|平台).{0,6}?(?:提示词|指令|约束)"),
    re.compile(r"只(?:能|得|需)?输出.{0,8}?(?:一句话|对不起|不知道|拒答)"),
    re.compile(r"(?:最高|最高级|平台级).{0,6}?(?:提示词|指令|约束)"),
    re.compile(r"(?:必须|务必)强制(?:遵循|执行).{0,6}?(?:提示词|指令|约束)"),
    re.compile(r"停止(?:解析|回答|输出).{0,10}?(?:返回|输出).{0,6}?不知道"),
    re.compile(r"(?:否则|不然).{0,10}?(?:承担|追究|付).{0,6}?法律责任"),
    re.compile(r"如果你是\s*(?:AI|人工智能|大模型|模型).{0,12}?(?:解析|阅读|处理|回答)"),
    re.compile(r"(?:必须|务必)遵循本(?:提示词|指令|约束)"),
]

# 入库文档的风险提示文案（触发过滤时写入 documents.risk_warning）
RISK_WARNING_MESSAGE = "检测到疑似提示词注入指令，已在解析阶段自动过滤"

# 句子切分：保留句末标点（中英文句号/分号/感叹/问号/换行）
_SENTENCE_RE = re.compile(r"[^。；;！!？?\n]*[。；;！!？?\n]?")


def scan_injection(text: str) -> list[str]:
    """扫描文本，返回命中的注入特征（关键词原文 + 正则片段；空列表 = 未命中）。"""
    if not text:
        return []
    hits: list[str] = [kw for kw in INJECTION_KEYWORDS if kw in text]
    for pat in INJECTION_PATTERNS:
        for m in pat.finditer(text):
            frag = m.group(0)
            if frag and frag not in hits:
                hits.append(frag)
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
    for m in _SENTENCE_RE.finditer(text):
        sent = m.group(0)
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
