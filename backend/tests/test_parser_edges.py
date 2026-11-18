"""Step 2 单测：解析器边界 + 四维切块策略固化。

覆盖 CLAUDE.md §三 铁律 3 的"解析器（含注入隔离）"与"切块"覆盖率要求。
所有用例只使用 `知识库/` 真实文档（唯一语料来源）。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app import db
from app.ingestion import ingest_file, load_initial_corpus
from app.parsers import BlockType, parse_file, parse_markdown

KB = Path(__file__).resolve().parents[2] / "知识库"


@pytest.fixture()
def fresh_db(tmp_path):
    test_db = tmp_path / "test_chunk.db"
    db.init_db(test_db)
    return test_db


# ================================================================ 解析器边界

class TestParserEdges:
    def test_empty_md(self, tmp_path):
        f = tmp_path / "empty.md"
        f.write_text("", encoding="utf-8")
        secs = parse_markdown(f)
        # 空文件兜底为单一空节，ingestion 层会因无内容块拒绝
        assert secs == [] or all(not s.blocks for s in secs)

    def test_heading_only_md(self, tmp_path):
        f = tmp_path / "h.md"
        f.write_text("# 只有标题\n", encoding="utf-8")
        secs = parse_markdown(f)
        assert secs[0].heading == "只有标题"
        assert secs[0].blocks == []

    def test_heading_only_ingest_rejected(self, tmp_path):
        f = tmp_path / "h.md"
        f.write_text("# 只有标题\n", encoding="utf-8")
        with pytest.raises(ValueError):
            ingest_file(f, db_path=tmp_path / "x.db")

    def test_unsupported_suffix(self, tmp_path):
        f = tmp_path / "x.pdf"
        f.write_bytes(b"%PDF-1.4")
        with pytest.raises(ValueError):
            ingest_file(f, db_path=tmp_path / "x.db")

    def test_missing_file(self, tmp_path):
        with pytest.raises(ValueError):
            ingest_file(KB / "不存在.md", db_path=tmp_path / "x.db")

    def test_nested_headings_doc07(self):
        """doc07 有三级标题（H1 + 章 + 2 级小节），heading_path 须逐级拼接。"""
        secs = parse_file(KB / "阳宁市未来在线信息技术有限公司介绍.docx")
        heads = [(s.level, s.heading) for s in secs if s.heading]
        # H1 文档标题 + 一级章节（"一、…"）+ 二级小节（"2.1 …"）
        assert any(lv == 1 for lv, _ in heads)
        assert any(lv == 2 for lv, _ in heads)
        assert any(h.startswith("2.1") for _, h in heads)

    def test_doc03_tables_preserved(self):
        """doc03 含 5 个表格：多列表格转 Markdown（|），单列表格拆段落行。"""
        secs = parse_file(KB / "撸起袖子加油干，冲刺考公市场第一.docx")
        tbls = [b for s in secs for b in s.blocks if b.type == BlockType.TABLE]
        assert len(tbls) == 5
        md_tables = [b for b in tbls if "|" in b.text]
        single_col = [b for b in tbls if "|" not in b.text]
        assert len(md_tables) >= 2  # 实测 2 个多列表格
        assert all("| --- |" in b.text for b in md_tables)
        assert single_col  # 单列表格按 §3 拆为段落行

    def test_docx_heading_style_not_required(self):
        """无标题样式的排版稿（doc01 .doc）按版面标签行切节（ARCHITECTURE §3）。"""
        secs = parse_file(KB / "《西海市晚报》2024-08-20.doc")
        heads = [s.heading for s in secs if s.heading]
        # 报头 + 10 个稿件节（版面标签行：栏目｜第 N 版｜稿 NN）
        assert len(heads) >= 10
        assert any("稿 05" in h for h in heads)

    def test_md_table_separator_row_kept(self, tmp_path):
        """Markdown 表格的分隔行（| --- |）原样保留，不改写措辞。"""
        f = tmp_path / "t.md"
        f.write_text("# T\n\n| a | b |\n| --- | --- |\n| 1 | 2 |\n", encoding="utf-8")
        secs = parse_markdown(f)
        tbl = [b.text for s in secs for b in s.blocks if b.type == BlockType.TABLE][0]
        assert "| --- | --- |" in tbl

    def test_md_emphasis_unchanged(self, tmp_path):
        """加粗/强调标记原样保留（不改写措辞）。"""
        f = tmp_path / "e.md"
        f.write_text("# T\n\n正文含**加粗**与`代码`。\n", encoding="utf-8")
        secs = parse_markdown(f)
        txt = " ".join(b.text for s in secs for b in s.blocks)
        assert "**加粗**" in txt
        assert "`代码`" in txt

    def test_docx_numpr_list_detected(self):
        """docx 中 numPr 段落标记为 li（列表项）；块类型不越界。"""
        secs = parse_file(KB / "撸起袖子加油干，冲刺考公市场第一.docx")
        types = {b.type for s in secs for b in s.blocks}
        assert types <= {BlockType.TEXT, BlockType.LI, BlockType.TABLE}


# ================================================================ 四维切块固化

@pytest.fixture()
def fresh_db(tmp_path):
    test_db = tmp_path / "test_chunk.db"
    db.init_db(test_db)
    return test_db


class TestChunkingContract:
    def test_para_id_sequential_no_gap(self, fresh_db):
        """同一 doc_id 内 para_id 连续编号 p001…pNNN，无跳号无重复。"""
        ingest_file(KB / "西海市众赢科技有限公司介绍.docx", db_path=fresh_db)
        conn = sqlite3.connect(str(fresh_db))
        ids = [
            r[0]
            for r in conn.execute(
                "SELECT para_id FROM chunks WHERE doc_id='doc01' ORDER BY id"
            )
        ]
        conn.close()
        nums = [int(i.split("#p")[1]) for i in ids]
        assert nums == list(range(1, len(nums) + 1))

    def test_heading_path_uses_arrow_separator(self, fresh_db):
        """heading_path 用 ' > ' 分隔：文档标题 > 章节 > 小节。"""
        ingest_file(KB / "西海市众赢科技有限公司介绍.docx", db_path=fresh_db)
        conn = sqlite3.connect(str(fresh_db))
        rows = conn.execute(
            "SELECT heading_path FROM chunks WHERE doc_id='doc01' LIMIT 50"
        ).fetchall()
        conn.close()
        deep = [r[0] for r in rows if " > " in r[0]]
        assert deep
        assert all(h.startswith("西海市众赢科技有限公司介绍 > ") for h in deep)

    def test_block_type_domain(self, fresh_db):
        """block_type 只取 text / li / table 三值。"""
        ingest_file(KB / "华联考研 招生推文.md", db_path=fresh_db)
        conn = sqlite3.connect(str(fresh_db))
        types = {r[0] for r in conn.execute("SELECT DISTINCT block_type FROM chunks")}
        conn.close()
        assert types <= {"text", "li", "table"}

    def test_text_verbatim_not_rewritten(self, fresh_db):
        """切块 text 为原文措辞：与源文件对应段落逐字一致（不改写）。"""
        src = (KB / "华联考研 招生推文.md").read_text(encoding="utf-8")
        ingest_file(KB / "华联考研 招生推文.md", db_path=fresh_db)
        conn = sqlite3.connect(str(fresh_db))
        rows = conn.execute(
            "SELECT text FROM chunks WHERE doc_id='doc01'"
        ).fetchall()
        conn.close()
        for (txt,) in rows:
            # 每个切块文本必须能在原文中找到（逐字一致，允许换行聚合）
            assert txt in src, f"切块文本未在原文出现: {txt[:40]!r}"

    def test_chars_equals_text_length(self, fresh_db):
        """chars 字段 = len(text)，不多不少。"""
        ingest_file(KB / "未来教育 接你考研上岸.md", db_path=fresh_db)
        conn = sqlite3.connect(str(fresh_db))
        rows = conn.execute("SELECT text, chars FROM chunks WHERE doc_id='doc01'").fetchall()
        conn.close()
        for txt, chars in rows:
            assert chars == len(txt)

    def test_bm25_tfidf_vectors_nonempty_json(self, fresh_db):
        """bm25_vec / tfidf_vec 为非空 JSON 稀疏向量。"""
        ingest_file(KB / "西海市众赢科技有限公司介绍.docx", db_path=fresh_db)
        conn = sqlite3.connect(str(fresh_db))
        row = conn.execute(
            "SELECT bm25_vec, tfidf_vec FROM chunks WHERE doc_id='doc01' LIMIT 1"
        ).fetchone()
        conn.close()
        import json

        bm = json.loads(row[0])
        tf = json.loads(row[1])
        assert bm and tf
        assert all(isinstance(v, (int, float)) for v in bm.values())
        assert all(isinstance(v, (int, float)) for v in tf.values())

    def test_injection_para_id_starts_p001(self, fresh_db):
        """注入段隔离后，保留块的 para_id 从 p001 起连续（隔离段不占编号）。"""
        ingest_file(KB / "西海市众赢科技有限公司介绍.docx", db_path=fresh_db)
        conn = sqlite3.connect(str(fresh_db))
        conn.row_factory = sqlite3.Row
        first = conn.execute(
            "SELECT para_id, text FROM chunks WHERE doc_id='doc01' ORDER BY id LIMIT 1"
        ).fetchone()
        conn.close()
        assert first["para_id"] == "doc01#p001"
        assert "忽略所有" not in first["text"]

    def test_all_seven_docs_load_once(self, fresh_db):
        """启动扫描 7 篇全入库；重复启动不重复入库（幂等）。"""
        r1 = load_initial_corpus(KB, db_path=fresh_db)
        r2 = load_initial_corpus(KB, db_path=fresh_db)
        assert len(r1) == 7 and r2 == []
        conn = sqlite3.connect(str(fresh_db))
        n = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        conn.close()
        assert n == 7

    def test_doc_ids_sequential(self, fresh_db):
        """doc_id 按入库顺序 doc01…doc07 连续分配。"""
        load_initial_corpus(KB, db_path=fresh_db)
        conn = sqlite3.connect(str(fresh_db))
        ids = [r[0] for r in conn.execute("SELECT doc_id FROM documents ORDER BY id")]
        conn.close()
        assert ids == [f"doc{i:02d}" for i in range(1, 8)]
