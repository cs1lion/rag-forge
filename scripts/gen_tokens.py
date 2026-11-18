#!/usr/bin/env python3
"""
gen_tokens.py — 从 DESIGN.md 的 ```tokens 代码块生成设计令牌实体文件。

产物：
  design/tokens.css   （CSS 自定义属性，前端直接消费）
  design/tokens.json  （机器可读，供构建/校验消费）

用法：
    python scripts/gen_tokens.py

本脚本只读取 DESIGN.md 的机器可解析令牌块，不引入其他来源，
保证"DESIGN.md 是唯一事实来源"的工程约束。
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DESIGN = ROOT / "DESIGN.md"
CSS_OUT = ROOT / "design" / "tokens.css"
JSON_OUT = ROOT / "design" / "tokens.json"


def extract_source() -> dict:
    text = DESIGN.read_text(encoding="utf-8")
    m = re.search(r"```tokens\s*\n(.*?)\n```", text, re.S)
    if not m:
        raise SystemExit("DESIGN.md 中未找到 ```tokens 代码块")
    return json.loads(m.group(1))


def ref_var(path: str) -> str:
    """'color.ink' -> '--color-ink'"""
    return "--" + path.replace(".", "-")


def build_css(tokens: dict) -> str:
    lines = [":root {"]
    for k, v in tokens.get("color", {}).items():
        lines.append(f"  --color-{k}: {v};")
    for k, v in tokens.get("semantic", {}).items():
        lines.append(f"  --{k}: var({ref_var(v)});")
    for k, v in tokens.get("font", {}).items():
        lines.append(f"  --font-{k}: {v};")
    for name, spec in tokens.get("type", {}).items():
        lines.append(f"  --text-{name}-size: {spec['size']}px;")
        lines.append(f"  --text-{name}-line-height: {spec['line-height']}px;")
        lines.append(f"  --text-{name}-weight: {spec['weight']};")
        lines.append(f"  --text-{name}-family: var({ref_var(spec['family'])});")
    for k, v in tokens.get("spacing", {}).items():
        lines.append(f"  --{k}: {v}px;")
    for k, v in tokens.get("radius", {}).items():
        lines.append(f"  --{k}: {v}px;")
    for k, v in tokens.get("shadow", {}).items():
        lines.append(f"  --{k}: {v};")
    for k, v in tokens.get("motion", {}).items():
        lines.append(f"  --{k}: {v};")
    lines.append("}")
    return "\n".join(lines) + "\n"


def main():
    tokens = extract_source()
    JSON_OUT.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(json.dumps(tokens, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    CSS_OUT.write_text("/* 由 DESIGN.md 自动生成，请勿手改；改 DESIGN.md 后重跑 scripts/gen_tokens.py */\n"
                       + build_css(tokens), encoding="utf-8")
    n = sum(len(v) for v in tokens.values())
    print(f"[ok] DESIGN.md tokens block -> design/tokens.css + design/tokens.json ({n} tokens)")


if __name__ == "__main__":
    main()
