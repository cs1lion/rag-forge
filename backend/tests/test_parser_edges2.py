"""Step 2 补充单测：解析器未覆盖边界（styles.xml 缺失 / outlineLvl / LibreOffice 兜底 / Markdown heading）。

目标：把我负责模块（app/parsers、app/ingestion）行覆盖率推到 ≥ 85% 以上并保持。
"""
from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from app import db
from app.ingestion import ingest_file
from app.parsers import (
    BlockType,
    _extract_doc_utf16,
    parse_docx,
    parse_file,
    parse_markdown,
    strip_dir_suffix,
)
from app.parsers.markdown import sections_from_text

KB = Path(__file__).resolve().parents[2] / "知识库"


@pytest.fixture()
def fresh_db(tmp_path):
    test_db = tmp_path / "test_edge.db"
    db.init_db(test_db)
    return test_db


# ---------------------------------------------------------------- markdown.py

class TestMarkdownModuleEdges:
    def test_heading_branch_creates_section(self):
        """sections_from_text 的 Markdown 标题分支（# ~ ######）。"""
        secs = sections_from_text("# 一级\n\n正文\n\n## 二级\n\n更多正文\n")
        heads = [(s.level, s.heading) for s in secs]
        assert (1, "一级") in heads
        assert (2, "二级") in heads

    def test_tag_line_creates_section(self):
        """版面标签行切节（`栏目｜第 N 版｜稿 NN`）。"""
        secs = sections_from_text("教育 · 要闻　｜　第 1 版　｜　稿 01\n正文一段\n")
        assert any(s.heading.startswith("教育 · 要闻") for s in secs)
        assert secs[0].blocks and secs[0].blocks[0].text == "正文一段"

    def test_fallback_empty_section(self):
        """空文本兜底为单一空节。"""
        secs = sections_from_text("")
        assert secs == [secs[0]]
        assert secs[0].heading == ""

    def test_parse_markdown_heading_branch(self, tmp_path):
        """parse_markdown 的 ATX 标题分支（# ~ ###### 全层级）。"""
        f = tmp_path / "h.md"
        f.write_text("# H1\n\n## H2\n\n###### H6\n\n正文\n", encoding="utf-8")
        secs = parse_markdown(f)
        levels = [s.level for s in secs if s.heading]
        assert levels == [1, 2, 6]

    def test_parse_markdown_li_branch(self, tmp_path):
        """parse_markdown 的有序/无序列表分支。"""
        f = tmp_path / "l.md"
        f.write_text("# T\n\n- 无序一\n* 无序二\n+ 无序三\n\n1. 有序一\n2) 有序二\n", encoding="utf-8")
        secs = parse_markdown(f)
        lis = [b.text for s in secs for b in s.blocks if b.type == BlockType.LI]
        assert "无序一" in lis and "无序二" in lis and "无序三" in lis
        assert "有序一" in lis

    def test_parse_markdown_table_branch(self, tmp_path):
        """parse_markdown 的 GFM 表格分支（多行表格聚合）。"""
        f = tmp_path / "tb.md"
        f.write_text(
            "# T\n\n| a | b |\n| --- | --- |\n| 1 | 2 |\n| 3 | 4 |\n\n段后\n",
            encoding="utf-8",
        )
        secs = parse_markdown(f)
        tbl = [b.text for s in secs for b in s.blocks if b.type == BlockType.TABLE]
        assert len(tbl) == 1
        assert "| 3 | 4 |" in tbl[0]
        # 表格后的段落独立成块
        texts = [b.text for s in secs for b in s.blocks if b.type == BlockType.TEXT]
        assert "段后" in texts

    def test_parse_markdown_fallback_empty(self, tmp_path):
        """无标题 Markdown 兜底为单一空节（level=0, heading=''）。"""
        f = tmp_path / "nf.md"
        f.write_text("只有段落\n没有标题\n", encoding="utf-8")
        secs = parse_markdown(f)
        assert secs[0].heading == ""
        assert secs[0].level == 0


# ---------------------------------------------------------------- parsers/__init__.py

class TestDocxEdges:
    def test_styles_xml_missing_fallback(self, tmp_path):
        """docx 无 word/styles.xml 时不崩溃（KeyError 兜底），段落仍可读。"""
        f = tmp_path / "no_styles.docx"
        with zipfile.ZipFile(f, "w") as z:
            z.writestr(
                "word/document.xml",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                "<w:body>"
                "<w:p><w:r><w:t>无样式段落</w:t></w:r></w:p>"
                "</w:body></w:document>",
            )
        secs = parse_docx(f)
        assert secs
        assert any(b.text == "无样式段落" for s in secs for b in s.blocks)

    def test_outlineLvl_heading(self, tmp_path):
        """outlineLvl 样式（非 heading name）也能识别为标题。"""
        f = tmp_path / "ol.docx"
        W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        with zipfile.ZipFile(f, "w") as z:
            styles = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                f'<w:style w:styleId="s1"><w:name w:val="自定义"/><w:pPr><w:outlineLvl w:val="1"/></w:pPr></w:style>'
                "</w:styles>"
            )
            doc = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                "<w:body>"
                f'<w:p><w:pPr><w:pStyle w:val="s1"/></w:pPr><w:r><w:t>大纲级标题</w:t></w:r></w:p>'
                "<w:p><w:r><w:t>普通段</w:t></w:r></w:p>"
                "</w:body></w:document>"
            )
            z.writestr("word/styles.xml", styles)
            z.writestr("word/document.xml", doc)
        secs = parse_docx(f)
        assert secs[0].heading == "大纲级标题"
        assert secs[0].level == 2  # outlineLvl=1 -> level=2

    def test_empty_table_returns_empty_string(self, tmp_path):
        """空表格（无 tr）不产生表格块。"""
        f = tmp_path / "et.docx"
        W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        with zipfile.ZipFile(f, "w") as z:
            doc = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                "<w:body>"
                "<w:tbl></w:tbl>"
                "<w:p><w:r><w:t>唯一段</w:t></w:r></w:p>"
                "</w:body></w:document>"
            )
            z.writestr("word/document.xml", doc)
        secs = parse_docx(f)
        tbls = [b for s in secs for b in s.blocks if b.type == BlockType.TABLE]
        assert tbls == []
        assert any(b.text == "唯一段" for s in secs for b in s.blocks)

    def test_numpr_list_item_detected(self, tmp_path):
        """numPr 段落标记为 li（列表项）。"""
        f = tmp_path / "li.docx"
        W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        with zipfile.ZipFile(f, "w") as z:
            doc = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                "<w:body>"
                f'<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr>'
                "<w:r><w:t>列表项一</w:t></w:r></w:p>"
                "<w:p><w:r><w:t>普通段</w:t></w:r></w:p>"
                "</w:body></w:document>"
            )
            z.writestr("word/document.xml", doc)
        secs = parse_docx(f)
        lis = [b.text for s in secs for b in s.blocks if b.type == BlockType.LI]
        assert "列表项一" in lis

    def test_heading_before_any_section_creates_root(self, tmp_path):
        """首个标题之前的块归入文档级节（level=0, heading=''）。"""
        f = tmp_path / "pre.docx"
        W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        with zipfile.ZipFile(f, "w") as z:
            doc = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                "<w:body>"
                "<w:p><w:r><w:t>抬头段</w:t></w:r></w:p>"
                "<w:p><w:r><w:t>标题来了</w:t></w:r></w:p>"
                "</w:body></w:document>"
            )
            z.writestr("word/document.xml", doc)
        secs = parse_docx(f)
        assert secs[0].heading == ""
        assert secs[0].blocks[0].text == "抬头段"

    def test_no_content_at_all_fallback(self, tmp_path):
        """docx 全空（无段落）兜底为单一空节。"""
        f = tmp_path / "blank.docx"
        with zipfile.ZipFile(f, "w") as z:
            z.writestr(
                "word/document.xml",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                "<w:body></w:body></w:document>",
            )
        secs = parse_docx(f)
        assert secs
        assert secs[0].heading == ""


class TestStripDirSuffix:
    def test_no_trailing_digit_unchanged(self):
        assert strip_dir_suffix("普通标题") == "普通标题"

    def test_trailing_digits_with_space(self):
        """带空格分隔的数字保守不剥离（防误伤正文中的数字串）。"""
        assert strip_dir_suffix("标题  12") == "标题  12"
        assert strip_dir_suffix("标题 12") == "标题 12"

    def test_all_digit_no_strip(self):
        """纯数字段（如页码本身）不剥离。"""
        assert strip_dir_suffix("123") == "123"

    def test_ascii_prefix_digit_not_stripped(self):
        """ASCII 结尾数字（如版本号 v2）不误剥。"""
        assert strip_dir_suffix("版本v2") == "版本v2"


class TestDocBinaryEdges:
    def test_extract_doc_utf16_rejects_noise(self):
        """二进制噪声（无中文标点/高频字）返回 None，即便 CJK 占比碰巧达标。"""
        raw = bytes(range(256)) * 4
        assert _extract_doc_utf16(raw) is None

    def test_extract_doc_utf16_rejects_pure_cjk_no_punct(self):
        """纯 CJK 无标点无高频字的伪文本也判为噪声。"""
        fake = "天地玄黄宇宙洪荒" * 20
        raw = fake.encode("utf-16-le")
        assert _extract_doc_utf16(raw) is None

    def test_extract_doc_utf16_accepts_real(self):
        """真实 .doc 提取成功且含正文。"""
        raw = (KB / "《西海市晚报》2024-08-20.doc").read_bytes()
        t = _extract_doc_utf16(raw)
        assert t is not None
        assert "西海市晚报" in t

    def test_parse_file_dispatch_md(self, tmp_path):
        f = tmp_path / "a.md"
        f.write_text("# T\n\n正文\n", encoding="utf-8")
        secs = parse_file(f)
        assert secs[0].heading == "T"

    def test_parse_file_dispatch_txt(self, tmp_path):
        f = tmp_path / "a.txt"
        f.write_text("# T\n\n正文\n", encoding="utf-8")
        secs = parse_file(f)
        assert secs[0].heading == "T"

    def test_parse_file_unsupported_suffix(self, tmp_path):
        f = tmp_path / "a.exe"
        f.write_bytes(b"\x00\x01")
        with pytest.raises(ValueError, match="不支持"):
            parse_file(f)

    def test_parse_file_missing(self):
        with pytest.raises(ValueError, match="不存在"):
            parse_file(KB / "无此文件.md")


class TestIngestEdge:
    def test_doc_ingest_injection_free(self, fresh_db):
        """.doc 报纸无注入特征，injection_flag=0。"""
        r = ingest_file(KB / "《西海市晚报》2024-08-20.doc", db_path=fresh_db)
        assert r.injection_flag == 0
        assert r.injection_excerpt_count == 0

    def test_docx_injection_flag_one(self, fresh_db):
        """.docx 注入段只记 1 次 flag，隔离段文本完整存档。"""
        r = ingest_file(KB / "西海市澎湃教育科技有限公司介绍.docx", db_path=fresh_db)
        assert r.injection_flag == 1
        assert r.injection_excerpt_count == 1
        assert r.chunk_count >= 60
