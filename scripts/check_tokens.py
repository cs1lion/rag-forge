#!/usr/bin/env python3
"""
check_tokens.py — 设计令牌三方一致性校验（100% 一致才通过）。

校验对象：
  1. DESIGN.md 提取结果  vs  design/tokens.json  （数值一致）
  2. DESIGN.md 提取结果  vs  design/tokens.css    （逐条声明一致）
  3. CSS 中 var(--x) 引用均在 :root 中定义

用法：
    python scripts/check_tokens.py
退出码：0=PASS，1=FAIL
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gen_tokens import build_css, build_tokens, section_text  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CSS = ROOT / "design" / "tokens.css"
JSONF = ROOT / "design" / "tokens.json"


def css_decls(css_text: str) -> dict:
    return {k: v.strip() for k, v in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", css_text)}


def main():
    tokens = build_tokens()
    errors = []

    # --- 1) tokens.json 与源一致 ------------------------------------------
    if not JSONF.exists():
        errors.append("design/tokens.json 不存在")
        j = {}
    else:
        j = json.loads(JSONF.read_text(encoding="utf-8"))
    if j != tokens:
        errors.append("tokens.json 与 DESIGN.md 提取结果不一致")
        for k in sorted(set(j) | set(tokens)):
            if j.get(k) != tokens.get(k):
                errors.append(f"  - 分组 '{k}' 不一致")

    # --- 2) tokens.css 与源逐条一致 ---------------------------------------
    expected = css_decls(build_css(tokens))
    if not CSS.exists():
        errors.append("design/tokens.css 不存在")
        actual = {}
    else:
        actual = css_decls(CSS.read_text(encoding="utf-8"))
    if expected != actual:
        errors.append("tokens.css 与 DESIGN.md 提取结果不一致")
        for k in sorted(set(expected) | set(actual)):
            if expected.get(k) != actual.get(k):
                errors.append(f"  - {k}: 期望 {expected.get(k)!r}，实际 {actual.get(k)!r}")

    # --- 3) 语义引用完整性 -------------------------------------------------
    for name, val in actual.items():
        for ref in re.findall(r"var\((--[\w-]+)\)", val):
            if ref not in actual:
                errors.append(f"  - CSS 引用 {ref}（被 {name} 使用）未定义")

    # --- 报告 -------------------------------------------------------------
    n_color = sum(len(t) for t in tokens["color"].values())
    n_all = n_color + len(tokens["type"]) + len(tokens["spacing"]) + \
        len(tokens["radius"]) + len(tokens["border-shadow"]) + len(tokens["motion"]) + \
        len(tokens["font"])
    print(f"[check] DESIGN.md 提取令牌总数: {n_all}（色板 {n_color}）")
    print(f"[check] design/tokens.json: {'一致' if j == tokens else '不一致'}")
    print(f"[check] design/tokens.css : {len(actual)}/{len(expected)} 条声明一致")
    if errors:
        print("\nRESULT: FAIL")
        for e in errors:
            print(e)
        sys.exit(1)
    print("\nRESULT: PASS — DESIGN.md / tokens.css / tokens.json 三方 100% 一致")


if __name__ == "__main__":
    main()
