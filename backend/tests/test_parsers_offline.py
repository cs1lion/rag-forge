"""离线解析器全路径回归套件（0-Skip，零外部语料依赖）。

覆盖 CLAUDE.md 铁律 3 要求的 L1(.md/.txt) / L2(.docx 含样式、列表、单/多列表格、目录页码剥离) /
L3(.doc OLE 校验、UTF-16 LE 流提取、sections_from_text 版面切节、LibreOffice 降级) 全分支。
"""
from __future__ import annotations

import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

from app.parsers import (
    BlockType,
    _extract_doc_utf16,
    _table_to_md,
    parse_doc_binary,
    parse_docx,
    parse_file,
    parse_markdown,
    strip_dir_suffix,
)
from app.parsers.markdown import sections_from_text


def _build_rich_docx(path: Path, *, include_styles: bool = True, empty: bool = False) -> None:
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    styles_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:style w:type="paragraph" w:styleId="H1"><w:name w:val="Heading 1"/></w:style>'
        '<w:style w:type="paragraph" w:styleId="CustomL2">'
        '<w:name w:val="SectionSub"/><w:pPr><w:outlineLvl w:val="1"/></w:pPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="BodyText"><w:name w:val="Normal"/></w:style>'
        "</w:styles>"
    )
    if empty:
        body = ""
    else:
        body = (
            "<w:p><w:r><w:t>封面抬头文本</w:t></w:r></w:p>"
            "<w:p><w:r><w:t>   </w:t></w:r></w:p>"
            "<w:p><w:pPr><w:pStyle w:val=\"H1\"/></w:pPr><w:r><w:t>一、公司概览1</w:t></w:r></w:p>"
            "<w:p><w:pPr><w:numPr/></w:pPr><w:r><w:t>核心业务线覆盖检索与视频合成</w:t></w:r></w:p>"
            "<w:p><w:pPr><w:pStyle w:val=\"CustomL2\"/></w:pPr><w:r><w:t>二级子节</w:t></w:r></w:p>"
            "<w:p><w:pPr><w:pStyle w:val=\"BodyText\"/></w:pPr><w:r><w:t>正文说明段落。</w:t></w:r></w:p>"
            "<w:tbl>"
            "<w:tr><w:tc><w:p><w:r><w:t>城市级别</w:t></w:r></w:p></w:tc>"
            "<w:tc><w:p><w:r><w:t>住宿上限</w:t></w:r></w:p></w:tc></w:tr>"
            "<w:tr><w:tc><w:p><w:r><w:t>一线城市</w:t></w:r></w:p></w:tc>"
            "<w:tc><w:p><w:r><w:t>680元</w:t></w:r></w:p></w:tc></w:tr>"
            "</w:tbl>"
            "<w:tbl>"
            "<w:tr><w:tc><w:p><w:r><w:t>单列表格第一行</w:t></w:r></w:p></w:tc></w:tr>"
            "<w:tr><w:tc><w:p><w:r><w:t>单列表格第二行</w:t></w:r></w:p></w:tc></w:tr>"
            "</w:tbl>"
        )
    doc_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("word/document.xml", doc_xml)
        if include_styles:
            zf.writestr("word/styles.xml", styles_xml)


def test_strip_dir_suffix_edge_cases():
    assert strip_dir_suffix("一、公司概览1") == "一、公司概览"
    assert strip_dir_suffix("第二章 制度说明12 ") == "第二章 制度说明"
    assert strip_dir_suffix("2.6 2026") == "2.6 2026"
    assert strip_dir_suffix("Section 1") == "Section 1"
    assert strip_dir_suffix("123") == "123"
    assert strip_dir_suffix("无页码标题") == "无页码标题"


def test_parse_markdown_full_syntax_and_empty(tmp_path):
    md = tmp_path / "full.md"
    md.write_text(
        "<!-- 单行元信息注释 -->\n"
        "<!--\n多行注释内容\n-->\n"
        "- 无标题前置无序列表项\n"
        "1. 无标题前置有序列表项\n\n"
        "# 一级标题\n\n"
        "普通段落第一行。\n\n"
        "| 指标 | 阈值 |\n"
        "| --- | --- |\n"
        "| 覆盖率 | 85% |\n\n"
        "## 二级标题\n"
        "2、 中文编号列表项\n",
        encoding="utf-8",
    )
    secs = parse_file(md)
    assert len(secs) == 3
    assert secs[0].blocks[0].type == BlockType.LI
    assert secs[1].heading == "一级标题"
    assert any(b.type == BlockType.TABLE and "覆盖率" in b.text for b in secs[1].blocks)
    assert any(b.type == BlockType.LI and "中文编号" in b.text for b in secs[2].blocks)
    assert secs[1].blocks[0].chars > 0

    txt = tmp_path / "empty.txt"
    txt.write_text("<!-- only comment -->\n", encoding="utf-8")
    empty_secs = parse_file(txt)
    assert len(empty_secs) == 1 and empty_secs[0].heading == ""


def test_parse_docx_styles_tables_lists_and_empty(tmp_path):
    rich = tmp_path / "rich.docx"
    _build_rich_docx(rich, include_styles=True, empty=False)
    secs = parse_file(rich)
    assert secs[0].level == 0 and secs[0].blocks[0].text == "封面抬头文本"
    h1 = next(s for s in secs if s.level == 1)
    assert h1.heading == "一、公司概览"  # 目录页码 1 被剥离
    assert any(b.type == BlockType.LI for b in h1.blocks)
    h2 = next(s for s in secs if s.level == 2)
    assert h2.heading == "二级子节"
    tables = [b for b in h2.blocks if b.type == BlockType.TABLE]
    assert len(tables) == 2
    assert "| 城市级别 | 住宿上限 |" in tables[0].text
    assert "单列表格第一行\n单列表格第二行" in tables[1].text

    # 缺少 styles.xml 且空内容时仍应安全兜底
    empty_docx = tmp_path / "empty.docx"
    _build_rich_docx(empty_docx, include_styles=False, empty=True)
    empty_secs = parse_docx(empty_docx)
    assert len(empty_secs) == 1 and empty_secs[0].blocks == []


def test_parse_doc_binary_utf16_and_libreoffice_fallback(tmp_path, monkeypatch):
    # 1. 非 OLE 文件魔数应报错
    bad_doc = tmp_path / "not_ole.doc"
    bad_doc.write_bytes(b"plain text not ole")
    with pytest.raises(ValueError):
        parse_file(bad_doc)

    # 2. 合法 OLE 魔数 + UTF-16 LE 中文正文（混入二进制噪声控制符）
    chinese_body = (
        "# 研发与运营制度汇编\r\n"
        "这是我们团队在研发与运营过程中整理的核心制度文件，里面有一套完整的说明与规范，"
        "所有人在日常工作里都需要严格遵循这些要求。我们的检索系统在本地运行，能够在有需要的时候"
        "快速定位到对应的政策段落，确保每一个回答都有可靠的来源依据，不会在没有事实支撑的情况下随意编造。\r\n"
        "要闻 | 第 1 版 | 稿 01\r\n"
        "这是一篇用于验证版面标签切节能力的正文内容，我们在系统里实现了解析器、切块、检索与验真。\r\n"
    )
    ole_header = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
    noise = b"\x00\x01\x02\x03\x04\x05"
    good_doc = tmp_path / "utf16_valid.doc"
    good_doc.write_bytes(ole_header + noise + chinese_body.encode("utf-16-le"))
    secs = parse_file(good_doc)
    assert any("研发与运营制度汇编" in s.heading for s in secs)
    assert sum(len(s.blocks) for s in secs) >= 1

    # 3. UTF-16 提取失败（无足够中文）+ 本机无 soffice → 抛出明确 ValueError
    short_doc = tmp_path / "binary_only.doc"
    short_doc.write_bytes(ole_header + b"\x00" * 64)
    assert _extract_doc_utf16(b"\x00" * 32) is None
    monkeypatch.setattr(shutil, "which", lambda cmd: None)
    with pytest.raises(ValueError):
        parse_doc_binary(short_doc)

    # 4. 模拟本机存在 soffice：走 LibreOffice 转换回退到 parse_docx
    monkeypatch.setattr(shutil, "which", lambda cmd: "/usr/bin/soffice")

    def fake_run(cmd, **kw):
        out_dir = Path(cmd[cmd.index("--outdir") + 1])
        _build_rich_docx(out_dir / "converted.docx", include_styles=True, empty=False)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    converted_secs = parse_doc_binary(short_doc)
    assert any(s.heading == "一、公司概览" for s in converted_secs)


def test_parse_file_errors_and_sections_from_text_empty(tmp_path):
    with pytest.raises(ValueError):
        parse_file(tmp_path / "does_not_exist.md")
    other = tmp_path / "sheet.xlsx"
    other.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError):
        parse_file(other)

    empty = sections_from_text("\n   \n")
    assert len(empty) == 1 and empty[0].heading == ""

    plain = sections_from_text("无标题纯文本行\n# 标题行\n正文行")
    assert plain[0].level == 0 and plain[1].heading == "标题行"
