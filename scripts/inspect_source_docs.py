# -*- coding: utf-8 -*-
"""
inspect_source_docs.py — 知识库原始文档解析策略验证（三级容错）

验证 知识库/ 下 .md / .docx / .doc 三种格式的真实解析行为，为
docs/ARCHITECTURE.md 的"三级容错解析策略"提供实测依据。

用法:
    python scripts/inspect_source_docs.py --src "知识库"
"""
import argparse
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
CJK_RE = re.compile(r"[一-鿿，。：；！？、《》（）「」0-9a-zA-Z%\-—…\s]+")


def parse_docx(path):
    z = zipfile.ZipFile(path)
    styles = {}
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
                    lvl = o.get(W + "val")
            styles[sid] = (name, lvl)
    except KeyError:
        pass
    root = ET.fromstring(z.read("word/document.xml"))
    body = root.find(W + "body")
    n_p = n_tbl = n_li = n_h = 0
    first = []
    for child in body:
        if child.tag == W + "p":
            ppr = child.find(W + "pPr")
            lvl = 0
            if ppr is not None:
                ps = ppr.find(W + "pStyle")
                if ps is not None:
                    sid = ps.get(W + "val") or ""
                    name, slvl = styles.get(sid, (sid, None))
                    m = re.match(r"^(heading|标题|head)\s*([1-9])$", (name or "").strip(), re.I)
                    if m:
                        lvl = int(m.group(2))
                    elif slvl is not None and str(slvl).isdigit():
                        n = int(slvl)
                        lvl = n + 1 if n < 6 else 0
            txt = "".join(t.text or "" for t in child.iter(W + "t")).replace(" ", " ").rstrip()
            if not txt.strip():
                continue
            if lvl:
                n_h += 1
            elif ppr is not None and ppr.find(W + "numPr") is not None:
                n_li += 1
            else:
                n_p += 1
            if len(first) < 3 and txt.strip():
                first.append(txt[:60])
        elif child.tag == W + "tbl":
            n_tbl += 1
    return dict(paras=n_p, headings=n_h, list_items=n_li, tables=n_tbl, first=first)


def probe_doc(path):
    raw = path.read_bytes()
    info = {"size": len(raw), "magic": raw[:8].hex()}
    info["ole_cfb"] = raw[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
    info["word_document_marker"] = b"Word.Document" in raw
    info["has_ole_stream_names"] = b"\x05Document" in raw or b"WordDocument" in raw
    u = raw.decode("utf-16-le", errors="ignore")
    runs = [r.strip() for r in CJK_RE.findall(u) if sum(1 for c in r if "一" <= c <= "鿿") >= 5]
    info["utf16_cjk_runs"] = len(runs)
    info["utf16_sample"] = runs[:3]
    try:
        g = raw.decode("gbk", errors="ignore")
        gruns = [r.strip() for r in CJK_RE.findall(g) if sum(1 for c in r if "一" <= c <= "鿿") >= 5]
        info["gbk_cjk_runs"] = len(gruns)
        info["gbk_sample"] = gruns[:3]
    except Exception as e:  # pragma: no cover
        info["gbk_err"] = str(e)
    return info


def read_md(path):
    txt = path.read_text(encoding="utf-8-sig")
    lines = [l for l in txt.splitlines() if l.strip()]
    return dict(lines=len(lines), first=[l[:60] for l in lines[:3]])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="知识库")
    args = ap.parse_args()
    src = Path(args.src)
    for p in sorted(src.iterdir()):
        if not p.is_file() or p.name.startswith("._") or p.name == ".DS_Store":
            continue
        suf = p.suffix.lower()
        try:
            if suf == ".docx":
                r = parse_docx(p)
                kind = "docx/OOXML"
            elif suf == ".doc":
                r = probe_doc(p)
                kind = "doc/binary"
            elif suf == ".md":
                r = read_md(p)
                kind = "md/plain"
            else:
                continue
            print(f"[{kind}] {p.name}")
            for k, v in r.items():
                print(f"    {k}: {v}")
        except Exception as e:
            print(f"[ERROR] {p.name}: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
