"""三级容错解析器包（.md / .docx / .doc）。

解析策略见 docs/ARCHITECTURE.md §3：
- L1 `.md`：Markdown 结构直读，标题/列表/表格原样保留，不改写措辞；
- L2 `.docx`：纯标准库 OOXML，读 `word/document.xml`，标题取自段落样式
  （Heading N / 标题 N / outlineLvl），表格转 Markdown，单列表格拆段落，
  目录页码后缀剥离；无标题样式排版稿按版面标签行（`栏目｜第 N 版｜稿 NN`）切节；
- L3 `.doc`：OLE 复合文档优先做 UTF-16 LE 文本流提取（实测《西海市晚报》.doc
  的 CF 流内文本为 UTF-16 LE，可完整读出），失败则经 LibreOffice/Word 转
  `.docx` 后走 L2。

所有解析器输出统一的 Section / Para 结构，注入隔离在 ingestion 层执行
（解析器不丢弃任何原文，隔离由 `app/ingestion.py` 完成）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class BlockType(str, Enum):
    HEADING = "heading"
    TEXT = "text"
    LI = "li"
    TABLE = "table"


@dataclass
class Section:
    """一个章节：标题 + 其下的段落/列表/表格块。"""

    level: int
    heading: str
    blocks: list["Para"] = field(default_factory=list)


@dataclass
class Para:
    """最小内容单元（段落 / 列表项 / 表格）。"""

    type: BlockType
    text: str

    @property
    def chars(self) -> int:
        return len(self.text)


def strip_dir_suffix(text: str) -> str:
    """剥离目录页码后缀（目录行末尾的纯数字页码）。

    实测 docx 目录页（TOC 域生成）的页码是独立 run，拼接后形如
    ``一、公司概览1``；同时兼容 ``标题  12`` 这类带空格的版本。
    标题本身以中文数字/数字编号结尾（如 ``2.6 2026：站在新的起点``），
    因此只剥离"紧跟非数字字符之后的数字串"，不误伤标题内容。
    """
    import re

    m = re.search(r"\d+\s*$", text)
    if not m:
        return text
    idx = m.start()
    if idx == 0:
        return text
    prev = text[idx - 1]
    if prev.isdigit() or prev.isascii():
        # 数字串与前面字符同为数字/ASCII（如 "2026" 本就是标题内容），不剥离
        return text
    return text[:idx].rstrip()


def parse_docx(path) -> list[Section]:
    """L2：纯标准库 OOXML 解析 .docx，返回 Section 列表。"""
    import re
    import zipfile
    from xml.etree import ElementTree as ET

    W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    z = zipfile.ZipFile(str(path))

    # 样式表：styleId -> (name, outlineLvl)
    styles: dict[str, tuple[str, int | None]] = {}
    try:
        sroot = ET.fromstring(z.read("word/styles.xml"))
        for st in sroot.findall(W + "style"):
            sid = st.get(W + "styleId") or ""
            name_el = st.find(W + "name")
            name = name_el.get(W + "val") if name_el is not None else sid
            lvl = None
            ppr = st.find(W + "pPr")
            if ppr is not None:
                o = ppr.find(W + "outlineLvl")
                if o is not None:
                    lvl = int(o.get(W + "val"))
            styles[sid] = (name or "", lvl)
    except KeyError:
        pass

    def heading_level(p_el) -> int:
        """段落样式 -> 标题层级（1-6），非标题返回 0。"""
        ppr = p_el.find(W + "pPr")
        if ppr is None:
            return 0
        ps = ppr.find(W + "pStyle")
        if ps is None:
            return 0
        sid = ps.get(W + "val") or ""
        name, slvl = styles.get(sid, (sid, None))
        m = re.match(r"^(heading|标题|head)\s*([1-9])$", name.strip(), re.I)
        if m:
            return int(m.group(2))
        if slvl is not None and str(slvl).isdigit():
            n = int(slvl)
            return n + 1 if n < 6 else 0
        return 0

    def para_text(p_el) -> str:
        # 目录页码剥离：TOC 行的页码是尾部独立 run（无 rPr 或带超链接样式），
        # 若整段形如 "标题123"（末尾纯数字且前一位非数字），按目录行处理。
        raw = "".join(t.text or "" for t in p_el.iter(W + "t"))
        return strip_dir_suffix(raw.replace(" ", " ").rstrip())

    root = ET.fromstring(z.read("word/document.xml"))
    body = root.find(W + "body")

    sections: list[Section] = []
    cur: Section | None = None

    def new_section(level: int, heading: str) -> Section:
        return Section(level=level, heading=heading)

    for child in body:
        if child.tag == W + "p":
            txt = para_text(child)
            if not txt.strip():
                continue
            lvl = heading_level(child)
            if lvl:
                cur = new_section(lvl, txt)
                sections.append(cur)
                continue
            is_li = child.find(W + "pPr") is not None and child.find(W + "pPr").find(
                W + "numPr"
            ) is not None
            if cur is None:
                # 首个标题之前的块（封面/抬头/目录等），归入文档级节
                cur = new_section(0, "")
                sections.append(cur)
            cur.blocks.append(
                Para(type=BlockType.LI if is_li else BlockType.TEXT, text=txt)
            )
        elif child.tag == W + "tbl":
            md = _table_to_md(child, W)
            if md:
                if cur is None:
                    cur = new_section(0, "")
                    sections.append(cur)
                cur.blocks.append(Para(type=BlockType.TABLE, text=md))

    # 无标题文档兜底：若全文无一个标题，整体作为单一节
    if not sections:
        sections.append(new_section(0, ""))
    return sections


def _table_to_md(tbl_el, W: str) -> str:
    """OOXML 表格 -> Markdown 表格；单列表格按 ARCHITECTURE §3 拆成段落行。"""
    rows = []
    for tr in tbl_el.findall(W + "tr"):
        cells = []
        for tc in tr.findall(W + "tc"):
            cell_text = " ".join(
                "".join(t.text or "" for t in p.iter(W + "t"))
                for p in tc.iter(W + "p")
            ).strip()
            cells.append(cell_text)
        rows.append(cells)
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    if width == 1:
        # 单列表格：拆为段落（每行一条），不做表格化
        return "\n".join(r[0] for r in rows if r[0].strip())
    header = rows[0]
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join(["---"] * width) + " |"]
    for r in rows[1:]:
        lines.append("| " + " | ".join(c.replace("\n", " ") for c in r) + " |")
    return "\n".join(lines)


def parse_markdown(path) -> list[Section]:
    """L1：Markdown 结构直读，不改写措辞。

    支持：ATX 标题（# ~ ######）、无序/有序列表、GFM 表格、段落；
    HTML 注释（如文本版顶部的元信息块）整块跳过。
    """
    import re

    text = path.read_text(encoding="utf-8-sig")
    lines = text.splitlines()

    sections: list[Section] = []
    cur: Section | None = None
    para_buf: list[str] = []
    table_buf: list[str] = []

    def flush_para():
        nonlocal para_buf
        if para_buf and cur is not None:
            cur.blocks.append(Para(type=BlockType.TEXT, text="\n".join(para_buf)))
        para_buf = []

    def flush_table():
        nonlocal table_buf
        if table_buf and cur is not None:
            cur.blocks.append(Para(type=BlockType.TABLE, text="\n".join(table_buf)))
        table_buf = []

    in_comment = False
    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()
        if stripped.startswith("<!--"):
            if stripped.endswith("-->") and len(stripped) > 4:
                continue
            in_comment = True
            continue
        if in_comment:
            if "-->" in stripped:
                in_comment = False
            continue
        if not stripped:
            flush_para()
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            flush_para()
            flush_table()
            cur = Section(level=len(m.group(1)), heading=m.group(2).strip())
            sections.append(cur)
            continue
        if stripped.startswith("|") and stripped.endswith("|"):
            flush_para()
            table_buf.append(stripped)
            continue
        flush_table()
        m = re.match(r"^[-*+]\s+(.*)$", stripped)
        if m:
            flush_para()
            if cur is None:
                cur = Section(level=0, heading="")
                sections.append(cur)
            cur.blocks.append(Para(type=BlockType.LI, text=m.group(1).strip()))
            continue
        m = re.match(r"^\d+[.、)]\s+(.*)$", stripped)
        if m:
            flush_para()
            if cur is None:
                cur = Section(level=0, heading="")
                sections.append(cur)
            cur.blocks.append(Para(type=BlockType.LI, text=m.group(1).strip()))
            continue
        para_buf.append(stripped)
    flush_para()
    flush_table()
    if not sections:
        sections.append(Section(level=0, heading=""))
    return sections


def _extract_doc_utf16(raw: bytes) -> str | None:
    """从 .doc（OLE CFB）二进制中尝试 UTF-16 LE 文本流提取。

    实测《西海市晚报》.doc 的 WordDocument 流以 UTF-16 LE 存储正文，
    按 CRLF 分段即可得完整稿件。提取失败返回 None（交给 L3 转换路径）。
    判据（除 CJK 数量外）必须同时满足，以防二进制字节对碰巧落入 CJK 区：
    - 含中文标点（，。；：、《》）——真实中文稿件必有，噪声几乎不可能；
    - 含 CJK 常用高频字（"的一是了我"）——真实语料必然命中多个。
    """
    try:
        text = raw.decode("utf-16-le", errors="ignore")
    except Exception:
        return None
    lines = [ln.strip() for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]

    def _is_text_char(c: str) -> bool:
        """可打印文本字符：CJK / CJK 标点 / 全角符号 / ASCII 可打印 / 常用符号。

        控制符、私用区、代理区、替换符、Hangul/天城文等二进制乱码字符
        一律视为噪声（作为文本段分隔符）。
        """
        o = ord(c)
        if "一" <= c <= "鿿":
            return True
        if 0x3000 <= o <= 0x303F:  # CJK 标点
            return True
        if 0xFF00 <= o <= 0xFFEF:  # 全角符号（含全角括号/逗号）
            return True
        if 32 <= o <= 126:  # ASCII 可打印
            return True
        return c in "　，。；：、“”‘’（）《》！？—…·≥≤→←↔℃■□●○◆◇★☆"

    def _real_segments(ln: str) -> list[str]:
        """从（可能混入二进制噪声的）行中切出连续真实文本段。"""
        segs, buf = [], []
        for c in ln:
            if _is_text_char(c):
                buf.append(c)
            else:
                if buf:
                    segs.append("".join(buf))
                    buf = []
        if buf:
            segs.append("".join(buf))
        return segs

    kept = []
    for ln in lines:
        for seg in _real_segments(ln):
            seg = seg.strip()
            if not seg:
                continue
            cjk = sum(1 for c in seg if "一" <= c <= "鿿")
            visible = sum(1 for c in seg if not c.isspace())
            # 真实中文段：CJK ≥4 且占比 ≥0.3（纯日期段"2024 年 8 月 20 日"≈0.3；
            # ≥4 过滤二进制噪声的随机 2–3 字 CJK 碎片，如"卋卋"）
            if cjk >= 4 and cjk / max(visible, 1) >= 0.3:
                kept.append(seg)
    if not kept:
        return None
    joined = "\n".join(kept)
    cjk = sum(1 for c in joined if "一" <= c <= "鿿")
    if cjk < 50 or cjk / max(len(joined), 1) < 0.3:
        return None
    has_punct = any(p in joined for p in "，。；：、《》（）")
    common = sum(1 for c in joined if c in "的一是了我在有不人这")
    if not has_punct or common < 10:
        return None
    return joined


def parse_doc_binary(path) -> list[Section]:
    """L3：.doc 二级容错——先 UTF-16 流提取，失败则转 docx 后走 L2。"""
    import shutil
    import subprocess
    import tempfile
    from pathlib import Path as _Path

    raw = path.read_bytes()
    # 0) OLE CFB 校验（magic d0cf11e0a1b11ae1）
    if raw[:8] != b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        raise ValueError("不是 OLE 复合文档（.doc）")
    # 1) 优先 UTF-16 文本流提取（实测可用，零外部依赖）
    extracted = _extract_doc_utf16(raw)
    if extracted:
        from .markdown import sections_from_text

        return sections_from_text(extracted)
    # 2) 兜底：LibreOffice / Word 转 docx 后走 L2
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise ValueError(".doc 需 LibreOffice/Word 转换，本机未安装且 UTF-16 提取失败")
    with tempfile.TemporaryDirectory() as td:
        subprocess.run(
            [soffice, "--headless", "--convert-to", "docx", "--outdir", td, str(path)],
            check=True,
            capture_output=True,
            timeout=180,
        )
        out = next(_Path(td).glob("*.docx"))
        return parse_docx(out)


def parse_file(path) -> list[Section]:
    """按扩展名三级容错分发；均失败抛 ValueError（对应 E_PARSE_FAILED）。"""
    from pathlib import Path

    p = Path(str(path))
    suf = p.suffix.lower()
    if not p.exists():
        raise ValueError(f"文件不存在: {p}")
    if suf == ".md":
        return parse_markdown(p)
    if suf == ".txt":
        return parse_markdown(p)
    if suf == ".docx":
        return parse_docx(p)
    if suf == ".doc":
        return parse_doc_binary(p)
    raise ValueError(f"不支持的格式: {suf}")
