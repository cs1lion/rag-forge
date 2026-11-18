#!/usr/bin/env python3
"""
check_tokens.py — 设计令牌三方一致性校验（100% 一致才通过）。

校验对象：
  1. DESIGN.md 的 ```tokens 源块  vs  design/tokens.json   （数值一致）
  2. DESIGN.md 的 ```tokens 源块  vs  design/tokens.css    （逐条声明一致）
  3. 语义令牌引用的完整性（var(--color-ink) 等必须在 :root 中定义）

用法：
    python scripts/check_tokens.py
退出码：0=PASS，1=FAIL
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gen_tokens import build_css, extract_source, ref_var  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CSS = ROOT / "design" / "tokens.css"
JSONF = ROOT / "design" / "tokens.json"


def css_decls(css_text: str) -> dict:
    return {k: v.strip() for k, v in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", css_text)}


def main():
    src = extract_source()
    errors = []

    # --- 1) tokens.json 与源块一致 -------------------------------------
    if not JSONF.exists():
        errors.append("design/tokens.json 不存在")
        j = {}
    else:
        j = json.loads(JSONF.read_text(encoding="utf-8"))
    if j != src:
        errors.append("tokens.json 与 DESIGN.md 源块不一致")
        for group in src:
            if j.get(group) != src[group]:
                errors.append(f"  - group '{group}' 不一致")

    # --- 2) tokens.css 与源块逐条一致 ----------------------------------
    expected = css_decls(build_css(src))
    if not CSS.exists():
        errors.append("design/tokens.css 不存在")
        actual = {}
    else:
        actual = css_decls(CSS.read_text(encoding="utf-8"))
    if expected != actual:
        errors.append("tokens.css 与 DESIGN.md 源块不一致")
        for k in sorted(set(expected) | set(actual)):
            if expected.get(k) != actual.get(k):
                errors.append(f"  - {k}: 期望 {expected.get(k)!r}，实际 {actual.get(k)!r}")

    # --- 3) 语义引用完整性 ---------------------------------------------
    for name, ref in src.get("semantic", {}).items():
        target = ref_var(ref)
        if target not in actual:
            errors.append(f"  - 语义令牌 --{name} 引用 {target} 未定义")

    # --- 报告 ----------------------------------------------------------
    total = sum(len(v) for v in src.values())
    print(f"[check] DESIGN.md 源块令牌数: {total}")
    print(f"[check] design/tokens.json: {'一致' if j == src else '不一致'}")
    print(f"[check] design/tokens.css : {len(actual)}/{len(expected)} 条声明一致")
    if errors:
        print("\nRESULT: FAIL")
        for e in errors:
            print(e)
        sys.exit(1)
    print("\nRESULT: PASS — DESIGN.md / tokens.css / tokens.json 三方 100% 一致")


if __name__ == "__main__":
    main()
