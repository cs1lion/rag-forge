"""Markdown 文本 -> Section 列表（供 L3 .doc UTF-16 提取结果复用）。"""
from __future__ import annotations

import re

from . import BlockType, Para, Section


def sections_from_text(text: str) -> list[Section]:
    """把纯文本（按行）按版面标签行 / 标题模式切节。

    识别两类切节信号：
    - Markdown 标题（# ~ ######）——L1 直读产物复用；
    - 版面标签行（`栏目｜第 N 版｜稿 NN`，ARCHITECTURE §3 无标题排版稿约定）。
    其余行按段落聚合。
    """
    tag_re = re.compile(r"^[^｜\n]{1,20}\s*｜[^｜\n]*第\s*\d+\s*版\s*｜\s*稿\s*\d+")
    sections: list[Section] = []
    cur: Section | None = None
    buf: list[str] = []

    def flush():
        nonlocal buf
        if buf and cur is not None:
            cur.blocks.append(Para(type=BlockType.TEXT, text="\n".join(buf)))
        buf = []

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            flush()
            cur = Section(level=len(m.group(1)), heading=m.group(2).strip())
            sections.append(cur)
            continue
        if tag_re.match(line):
            flush()
            cur = Section(level=1, heading=line)
            sections.append(cur)
            continue
        if cur is None:
            cur = Section(level=0, heading="")
            sections.append(cur)
        buf.append(line)
    flush()
    if not sections:
        sections.append(Section(level=0, heading=""))
    return sections
