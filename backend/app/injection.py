"""注入隔离：可疑特征词表与段落扫描（入库即执行）。

词表与 `知识库_文本版/manifest.json` 的 `flags.prompt_injection_keywords`
同源（ARCHITECTURE §3）；任何 Agent 不得改写该词表内容，仅可在此引用。
"""
from __future__ import annotations

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


def scan_injection(text: str) -> list[str]:
    """扫描文本，返回命中的注入特征词表（空列表 = 未命中）。"""
    return [kw for kw in INJECTION_KEYWORDS if kw in text]
