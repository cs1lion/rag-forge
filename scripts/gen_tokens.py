#!/usr/bin/env python3
"""
gen_tokens.py — 从 DESIGN.md 生成设计令牌实体文件。

产物：
  design/tokens.css   （CSS 自定义属性，前端直接消费）
  design/tokens.json  （机器可读，供构建/校验消费）

本脚本只读取 DESIGN.md，不引入其他来源，保证"DESIGN.md 是唯一事实来源"。

提取规则（对应 DESIGN.md 章节）：
  §3 色彩      → 色板表（--nb-bg/text/accent…）+ 功能色块表（--nb-tint-*）
  §4 字体与层级 → 字体族 + 6 个字号层级（页标题/区块标题/卡片标题/正文/元信息/微标签）
  §5 间距容器   → 间距基数序列、圆角、描边、阴影
  §7 动效      → 时长档位、缓动函数、入场错位步进
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DESIGN = ROOT / "DESIGN.md"
CSS_OUT = ROOT / "design" / "tokens.css"
JSON_OUT = ROOT / "design" / "tokens.json"

# ---------------------------------------------------------------- 提取工具


def section(text: str, heading: str, next_heading: str) -> str:
    """取 ## heading 与下一个 ## 之间的正文。"""
    m = re.search(rf"^##\s+{re.escape(heading)}\s*\n(.*?)(?=^##\s|\Z)", text, re.S | re.M)
    if not m:
        raise SystemExit(f"DESIGN.md 中未找到章节: {heading}")
    return m.group(1)


def table_rows(text: str) -> list[list[str]]:
    """取章节内 markdown 表格的数据行（跳过表头与分隔行）。

    注意：不去反引号——功能色块表一个单元格内含成对 `名` `值`，
    去反引号会破坏配对；令牌名/值的反引号由 named_tokens / _strip 统一处理。
    """
    rows = []
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if all(set(c) <= set("-: ") for c in cells):
            continue
        if cells and cells[0] in ("角色", "名称", "层级", "令牌"):
            continue
        rows.append(cells)
    return rows


def named_tokens(cell: str) -> list[tuple[str, str]]:
    """单元格内所有 `名` `值` 对（功能色块表一行两对）。"""
    out = []
    for m in re.finditer(r"`(--[\w-]+)`\s+`([^`]+)`", cell):
        out.append((m.group(1), m.group(2)))
    return out


def _strip_backticks(s: str) -> str:
    return s.strip().strip("`")


# ---------------------------------------------------------------- 各节提取


def extract_color() -> dict:
    sec = section(section_text(), "3. 色彩", "4.")
    rows = table_rows(sec)
    base, text, accent, tint = {}, {}, {}, {}
    for cells in rows:
        flat = [c for c in cells if c]
        if not flat:
            continue
        joined = " | ".join(flat)
        pairs = named_tokens(joined)
        # 功能色块表：一行含两对 `名` `值`，且名带 tint
        if len(pairs) >= 2 and all("tint" in n for n, _ in pairs):
            for n, v in pairs:
                tint[n] = v
            continue
        # 常规色板表：第 2 列是令牌名、第 3 列是值（带反引号，统一去掉）
        if len(flat) >= 3 and flat[1].strip("`").startswith("--"):
            name = flat[1].strip("`")
            val = flat[2].strip("`")
            if name.startswith("--nb-bg"):
                base[name] = val
            elif name.startswith("--nb-text"):
                text[name] = val
            elif name.startswith("--nb-accent"):
                accent[name] = val
            elif name.startswith("--nb-border"):
                base[name] = val
    return {"base": base, "text": text, "accent": accent, "tint": tint}


def extract_type() -> dict:
    sec = section(section_text(), "4. 字体与层级", "5.")
    rows = table_rows(sec)
    names = ["page-title", "section-title", "card-title", "body", "meta", "micro-label"]
    out = {}
    for i, cells in enumerate(rows):
        flat = [c for c in cells if c]
        if len(flat) < 5 or i >= len(names):
            continue
        size_cell = flat[1]
        size_m = re.search(r"(\d+)px", size_cell)
        clamp_m = re.search(r"`(clamp\([^)]+\))`", size_cell)
        zh_m = re.search(r"中文\s*(\d+)px", size_cell)
        lh_m = re.search(r"([\d.]+)", flat[2])
        weight_m = re.search(r"(\d+)", flat[3])
        ls_m = re.search(r"字距\s*\+([\d.]+em)", flat[4] if len(flat) > 4 else "")
        if not (size_m and lh_m and weight_m):
            continue
        key = names[i]
        color_col = flat[4]
        color_ref = "--nb-text"
        if color_col.startswith("次文字"):
            color_ref = "--nb-text-secondary"
        elif color_col.startswith("说明文字"):
            color_ref = "--nb-text-tertiary"
        spec = {
            "size": int(size_m.group(1)),
            "line-height": float(lh_m.group(1)),
            "weight": int(weight_m.group(1)),
            "color": color_ref,
        }
        if clamp_m:
            spec["size-clamp"] = clamp_m.group(1)
        if zh_m:
            spec["size-zh"] = int(zh_m.group(1))
        if ls_m:
            spec["letter-spacing"] = f"+{ls_m.group(1)}"
        out[key] = spec
    # 中文上调规则（§4 末段）
    out["_zh_note"] = "中文正文比英文上调一档；正文行宽 32–40 汉字（65–75 字符），移动端 20–24 汉字"
    return out


def extract_font_family() -> dict:
    sec = section(section_text(), "4. 字体与层级", "5.")
    m = re.search(r"拉丁字符用\s*(.+?)\s*；中文回落到\s*`([^`]+)`", sec)
    if not m:
        return {"family-sans": "'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', sans-serif"}
    return {"family-sans": f"{m.group(2)}, system-ui, sans-serif"}


def extract_spacing() -> dict:
    sec = section(section_text(), "5. 间距、容器与圆角", "6.")
    m = re.search(r"间距基数\s*(\d+)，只用这些值：`([\d\s]+)`", sec)
    if not m:
        return {}
    vals = [int(x) for x in m.group(2).split()]
    return {f"space-{v}": v for v in vals}


def extract_radius() -> dict:
    sec = section(section_text(), "5. 间距、容器与圆角", "6.")
    out = {}
    for name, val in re.findall(r"`(--nb-radius-[\w-]+)`\s+(\d+)px", sec):
        out[name] = int(val)
    return out


def extract_border_shadow() -> dict:
    sec = section(section_text(), "5. 间距、容器与圆角", "6.")
    out = {}
    m = re.search(r"描边：统一\s*(\d+)px，颜色\s*(`--nb-border`|--nb-border)", sec)
    if m:
        out["border-width"] = int(m.group(1))
    m = re.search(r"仅浮层（下拉、气泡）用\s*`([^`]+)`", sec)
    if m:
        out["shadow-float"] = m.group(1)
    out["shadow-none"] = "none"
    return out


def extract_motion() -> dict:
    sec = section(section_text(), "7. 动效", "8.")
    out = {}
    m = re.search(r"悬停/聚焦反馈：(\d+)–(\d+)ms，`([\w.,()-]+)`", sec)
    if m:
        out["duration-fast"] = f"{m.group(1)}ms"
        out["duration-normal"] = f"{m.group(2)}ms"
        out["ease-out"] = m.group(3)
    m = re.search(r"面板展开、抽屉：(\d+)–(\d+)ms，进入 ease-out，退出\s*([\d%–]+)\s*时长、(ease-in)", sec)
    if m:
        out["duration-slow"] = f"{m.group(2)}ms"
        out["ease-in"] = m.group(4)
        out["duration-exit"] = f"60–70% of duration-slow（原文：退出 {m.group(3)} 时长）"
    m = re.search(r"列表项入场错位：(\d+)–(\d+)ms\s*递增，最多\s*(\d+)\s*项", sec)
    if m:
        out["stagger-step"] = f"{m.group(1)}–{m.group(2)}ms"
        out["stagger-max"] = int(m.group(3))
    out["reduced-motion"] = "prefers-reduced-motion: reduce 时过渡降为 0ms，保留最终状态"
    return out


def section_text() -> str:
    return DESIGN.read_text(encoding="utf-8")


# ---------------------------------------------------------------- 组装输出


def build_tokens() -> dict:
    color = extract_color()
    return {
        "color": color,
        "font": extract_font_family(),
        "type": extract_type(),
        "spacing": extract_spacing(),
        "radius": extract_radius(),
        "border-shadow": extract_border_shadow(),
        "motion": extract_motion(),
    }


def build_css(tokens: dict) -> str:
    lines = [":root {"]
    for group in ("color", "font", "type", "spacing", "radius", "border-shadow", "motion"):
        g = tokens.get(group, {})
        if group == "color":
            for subgroup in ("base", "text", "accent", "tint"):
                for k, v in g.get(subgroup, {}).items():
                    lines.append(f"  {k}: {v};")
        elif group == "font":
            for k, v in g.items():
                lines.append(f"  --font-{k}: {v};")
        elif group == "type":
            for k, v in g.items():
                if k.startswith("_"):
                    continue
                lines.append(f"  --text-{k}-size: {v['size']}px;")
                if "size-clamp" in v:
                    lines.append(f"  --text-{k}-size-clamp: {v['size-clamp']};")
                if "size-zh" in v:
                    lines.append(f"  --text-{k}-size-zh: {v['size-zh']}px;")
                lines.append(f"  --text-{k}-line-height: {v['line-height']};")
                lines.append(f"  --text-{k}-weight: {v['weight']};")
                lines.append(f"  --text-{k}-color: var({v['color']});")
                if "letter-spacing" in v:
                    lines.append(f"  --text-{k}-letter-spacing: {v['letter-spacing']};")
        elif group == "spacing":
            for k, v in g.items():
                lines.append(f"  --space-{k.split('-')[1]}: {v}px;")
        elif group == "radius":
            for k, v in g.items():
                lines.append(f"  {k}: {v}px;")
        elif group == "border-shadow":
            for k, v in g.items():
                if k == "border-width":
                    lines.append(f"  --border-width: {v}px;")
                else:
                    lines.append(f"  --{k}: {v};")
        elif group == "motion":
            for k, v in g.items():
                if k == "reduced-motion":
                    continue  # 说明性规则，不是 CSS 值
                if k == "duration-exit":
                    continue  # 说明性文字，非确定性值
                lines.append(f"  --{k}: {v};")
        else:
            for k, v in g.items():
                lines.append(f"  --{k}: {v};")
    lines.append("}")
    return "\n".join(lines) + "\n"


def main():
    tokens = build_tokens()
    JSON_OUT.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(json.dumps(tokens, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    CSS_OUT.write_text("/* 由 DESIGN.md 自动生成，请勿手改；改 DESIGN.md 后重跑 scripts/gen_tokens.py */\n"
                       + build_css(tokens), encoding="utf-8")
    n = sum(len(t) for t in tokens["color"].values())
    print(f"[ok] DESIGN.md -> design/tokens.css + design/tokens.json "
          f"(color {n} + type {len(tokens['type'])} + space {len(tokens['spacing'])} + "
          f"radius {len(tokens['radius'])} + shadow {len(tokens['border-shadow'])} + "
          f"motion {len(tokens['motion'])})")


if __name__ == "__main__":
    main()
