"""三页问答视频渲染（PIL 主路径 + Remotion 可选）。

版式（DESIGN.md 编辑型工作台）：
- 画布 1280×720 白底；顶栏 56px（1px 描边）；顶部 3px 进度条（--nb-accent）
  随全局时间轴 0%→100% 连续增长；
- 居中主卡片：白底 + 1px #E1E3E6 描边 + 12px 圆角 + 48px 内边距；
- 文本容器：max-width 88%、word-break/overflow-wrap: break-word、行高 1.65，
  任意长度中文自动折行，绝不越出卡片/画布；
- 页切换 180ms（24fps ≈ 5 帧）柔和淡入 + 8px 微位移。

三页：
  question  问题检索（蓝色微标签胶囊 + 36px 粗体问题 + 来源提示）
  answer    核心解答（问题回顾 + 大号加粗结论 + ≤3 条要点，数字强调）
  citations 引用参考文档（文档卡片：文件名 / 章节路径 / 原文摘录）

每页时长由 video.py 依据该页 TTS 语音的真实时长（+0.4s 呼吸停顿）写入
`page["frames"]`，渲染端严格按页边界切页，实现音画同步。

契约：render_pages(pages, out_path, prefer="remotion") -> {path, seconds, engine, pages}
"""
from __future__ import annotations

import asyncio
import json
import re
import shutil
from pathlib import Path

# 跨平台中文字体栈：防止 Linux/无中文字体环境下渲染成方块乱码。
# 取值顺序：macOS（PingFang）→ Windows（Microsoft YaHei）→ Linux（Noto/Source Han）。
CROSS_PLATFORM_FONT = (
    '"PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", '
    '"Source Han Sans SC", sans-serif'
)

# 视频规格（与 DESIGN.md 编辑型工作台一致：白底 + 1px 描边）
W, H = 1280, 720
FPS = 24
TRANSITION_FRAMES = 5  # 180ms @ 24fps
DEFAULT_PAGE_SECONDS = 4

# design/tokens.css 的色板/字号/间距（渲染兜底与校验用，真值以 tokens.css 为准）
TOKENS = {
    "bg": "#FFFFFF",
    "bg_subtle": "#F7F8F9",
    "border": "#E1E3E6",
    "text": "#1F1F1F",
    "text_secondary": "#444746",
    "text_tertiary": "#5E5E5E",
    "accent": "#1A73E8",
    "accent_soft": "#E8F0FE",
    "tint_blue_bg": "#E3EEFC",
    "tint_blue_ink": "#174EA6",
    "tint_green_bg": "#E4F3E8",
    "tint_green_ink": "#1E6B3A",
    "radius_md": 12,
    "space_16": 16,
    "space_24": 24,
    "space_32": 32,
    "font_sans": CROSS_PLATFORM_FONT,
}

_NUM_RE = re.compile(r"(\d+(?:\.\d+)?%?)")


def _tokens_from_css() -> dict:
    """从 design/tokens.css 读真实令牌（三方一致校验的产物），覆盖默认值。"""
    css = None
    for cand in (
        Path(__file__).resolve().parents[3] / "design" / "tokens.css",
        Path(__file__).resolve().parents[2] / "design" / "tokens.css",
    ):
        if cand.exists():
            css = cand.read_text(encoding="utf-8")
            break
    if not css:
        return TOKENS
    out = dict(TOKENS)
    mapping = {
        "--nb-bg": "bg",
        "--nb-bg-subtle": "bg_subtle",
        "--nb-border": "border",
        "--nb-text": "text",
        "--nb-text-secondary": "text_secondary",
        "--nb-text-tertiary": "text_tertiary",
        "--nb-accent": "accent",
        "--nb-accent-soft": "accent_soft",
        "--nb-tint-blue-bg": "tint_blue_bg",
        "--nb-tint-blue-ink": "tint_blue_ink",
        "--nb-tint-green-bg": "tint_green_bg",
        "--nb-tint-green-ink": "tint_green_ink",
        "--nb-radius-md": "radius_md",
    }
    for var, key in mapping.items():
        m = re.search(rf"{re.escape(var)}:\s*([^;]+);", css)
        if m:
            out[key] = m.group(1).strip()
    return out


def _page_frames(page: dict) -> int:
    frames = page.get("frames")
    try:
        frames = int(frames)
    except (TypeError, ValueError):
        frames = int(round(float(page.get("duration") or DEFAULT_PAGE_SECONDS) * FPS))
    return max(1, frames)


# ================================================================ Remotion

_ROOT_TSX = '''\
import React from "react";
import { Composition, getInputProps } from "remotion";
import { QAVideo } from "./QAVideo";

export const RemotionRoot: React.FC = () => {
  const props = getInputProps() as any;
  return (
    <Composition
      id="QAVideo"
      component={QAVideo}
      durationInFrames={props.durationInFrames}
      fps={props.fps}
      width={props.width}
      height={props.height}
      defaultProps={{ pages: props.pages, fps: props.fps }}
    />
  );
};
'''

_QA_TSX = '''\
import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate, Easing } from "remotion";

const C = {
  bg: "__BG__", subtle: "__BG_SUBTLE__", border: "__BORDER__",
  text: "__TEXT__", secondary: "__TEXT_SECONDARY__", tertiary: "__TEXT_TERTIARY__",
  accent: "__ACCENT__", accentSoft: "__ACCENT_SOFT__",
  blueBg: "__TINT_BLUE_BG__", blueInk: "__TINT_BLUE_INK__",
};
const FONT = "__FONT__";

// 折行保障：文本容器统一 max-width 88% + break-word + 行高 1.65
const text: React.CSSProperties = {
  maxWidth: "88%",
  whiteSpace: "normal",
  wordBreak: "break-word",
  overflowWrap: "break-word",
  lineHeight: 1.65,
};

const Pill: React.FC<{ label: string }> = ({ label }) => (
  <span style={{ ...text, display: "inline-flex", alignItems: "center", padding: "4px 14px",
    borderRadius: 999, background: C.blueBg, color: C.blueInk, fontSize: 13,
    fontWeight: 600, letterSpacing: "0.02em", alignSelf: "flex-start", lineHeight: 1.3 }}>
    {label}
  </span>
);

const Rich: React.FC<{ value: string; size: number; weight?: number; color: string }> = ({ value, size, weight = 400, color }) => (
  <span style={{ fontSize: size, fontWeight: weight, color }}>
    {String(value || "").split(/(\\d+(?:\\.\\d+)?%?)/).map((part, i) =>
      /^\\d/.test(part)
        ? <span key={i} style={{ color: C.accent, fontWeight: 700 }}>{part}</span>
        : <span key={i}>{part}</span>
    )}
  </span>
);

const QuestionPage: React.FC<{ page: any }> = ({ page }) => (
  <>
    <Pill label={page.label || "问题检索"} />
    <div style={{ ...text, marginTop: 28, fontSize: 36, fontWeight: 700, color: C.text }}>
      {page.title}
    </div>
    <div style={{ ...text, marginTop: 32, fontSize: 14, color: C.tertiary }}>{page.meta}</div>
  </>
);

const AnswerPage: React.FC<{ page: any }> = ({ page }) => (
  <>
    <Pill label={page.label || "核心解答"} />
    <div style={{ ...text, marginTop: 18, fontSize: 14, color: C.tertiary }}>{page.recap}</div>
    <div style={{ ...text, marginTop: 14, fontSize: 30, fontWeight: 700, color: C.text }}>
      <Rich value={page.summary} size={30} weight={700} color={C.text} />
    </div>
    <div style={{ maxWidth: "88%", marginTop: 28, display: "flex", flexDirection: "column", gap: 16 }}>
      {(page.points || []).map((p: string, i: number) => (
        <div key={i} style={{ display: "flex", gap: 12 }}>
          <span style={{ width: 7, height: 7, marginTop: 12, borderRadius: 999, background: C.accent, flexShrink: 0 }} />
          <span style={{ ...text, fontSize: 18, color: C.secondary }}>
            <Rich value={p} size={18} color={C.secondary} />
          </span>
        </div>
      ))}
    </div>
  </>
);

const CitationsPage: React.FC<{ page: any }> = ({ page }) => (
  <>
    <Pill label={page.label || "引用参考文档"} />
    <div style={{ maxWidth: "88%", marginTop: 22, display: "flex", flexDirection: "column", gap: 14 }}>
      {(page.citations || []).map((c: any, i: number) => (
        <div key={i} style={{ border: `1px solid ${C.border}`, borderRadius: 8, padding: "14px 18px", background: C.bg }}>
          <div style={{ ...text, fontSize: 15, fontWeight: 600, color: C.text }}>{c.source_file}</div>
          <div style={{ ...text, marginTop: 4, fontSize: 12, color: C.tertiary }}>{c.heading_path}</div>
          <div style={{ ...text, marginTop: 8, padding: "8px 12px", borderRadius: 6, background: C.subtle,
            fontSize: 13, color: C.secondary }}>{c.snippet}</div>
        </div>
      ))}
    </div>
  </>
);

export const QAVideo: React.FC<{ pages: any[]; fps: number }> = ({ pages, fps }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const seq = (pages || []).map((p: any) => Math.max(1, Math.round(p.frames || 4 * fps)));
  const total = seq.reduce((a: number, b: number) => a + b, 0);

  let idx = 0, start = 0;
  for (let i = 0; i < seq.length; i++) {
    if (frame < start + seq[i]) { idx = i; break; }
    start += seq[i];
    idx = i;
  }
  const local = frame - start;
  const page = (pages || [])[idx] || {};
  const enter = interpolate(local, [0, 5], [0, 1], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.cubic),
  });
  const progress = Math.min(1, (frame + 1) / Math.max(durationInFrames, total, 1));

  return (
    <AbsoluteFill style={{ background: C.bg, fontFamily: FONT }}>
      <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: 56,
        borderBottom: `1px solid ${C.border}`, display: "flex", alignItems: "center",
        justifyContent: "space-between", paddingLeft: 24, paddingRight: 24 }}>
        <span style={{ fontSize: 16, fontWeight: 500, color: C.text }}>知识库问答 · 视频工作台</span>
        <span style={{ fontSize: 12, color: C.tertiary }}>{idx + 1} / {Math.max(seq.length, 1)}</span>
      </div>
      {/* 顶部进度条：随全局时间轴连续增长 */}
      <div style={{ position: "absolute", top: 56, left: 0, height: 3,
        width: `${progress * 100}%`, background: C.accent }} />
      {/* 居中主卡片 */}
      <div style={{ position: "absolute", left: "6%", right: "6%", top: 88, bottom: 72,
        boxSizing: "border-box", background: C.bg, border: `1px solid ${C.border}`,
        borderRadius: 12, padding: 48, display: "flex", flexDirection: "column",
        justifyContent: "center", opacity: enter, transform: `translateY(${(1 - enter) * 8}px)` }}>
        {page.kind === "question" && <QuestionPage page={page} />}
        {page.kind === "answer" && <AnswerPage page={page} />}
        {page.kind === "citations" && <CitationsPage page={page} />}
      </div>
      <div style={{ position: "absolute", left: 0, right: 0, bottom: 48, height: 1, background: C.border }} />
      <div style={{ position: "absolute", left: 24, bottom: 16, fontSize: 12, color: C.tertiary }}>
        知识库问答 · 自动生成
      </div>
    </AbsoluteFill>
  );
};
'''

_PKG_JSON = {
    "name": "qa-video-render",
    "version": "1.0.0",
    "private": True,
    "type": "module",
    "dependencies": {
        "remotion": "^4.0.0",
        "react": "^18.3.1",
        "react-dom": "^18.3.1",
    },
    "devDependencies": {"@remotion/cli": "^4.0.0", "typescript": "^5.5.4"},
}

_TSCONFIG = {
    "compilerOptions": {
        "target": "ES2020",
        "module": "ESNext",
        "moduleResolution": "bundler",
        "jsx": "react-jsx",
        "strict": True,
        "esModuleInterop": True,
        "skipLibCheck": True,
    },
    "include": ["src"],
}


def _ensure_project(workdir: Path, tokens: dict) -> Path:
    """生成一次性 Remotion 工程，返回工程根（模板逐字取 tokens.css 令牌）。"""
    src = workdir / "src"
    src.mkdir(parents=True, exist_ok=True)
    qa = _QA_TSX
    for key, placeholder in (
        ("bg", "__BG__"),
        ("bg_subtle", "__BG_SUBTLE__"),
        ("border", "__BORDER__"),
        ("text", "__TEXT__"),
        ("text_secondary", "__TEXT_SECONDARY__"),
        ("text_tertiary", "__TEXT_TERTIARY__"),
        ("accent", "__ACCENT__"),
        ("accent_soft", "__ACCENT_SOFT__"),
        ("tint_blue_bg", "__TINT_BLUE_BG__"),
        ("tint_blue_ink", "__TINT_BLUE_INK__"),
        ("font_sans", "__FONT__"),  # CROSS_PLATFORM_FONT（见 TOKENS 默认值）
    ):
        qa = qa.replace(placeholder, tokens[key])
    (src / "QAVideo.tsx").write_text(qa, encoding="utf-8")
    (src / "Root.tsx").write_text(_ROOT_TSX, encoding="utf-8")
    (workdir / "package.json").write_text(json.dumps(_PKG_JSON, ensure_ascii=False, indent=2), encoding="utf-8")
    (workdir / "tsconfig.json").write_text(json.dumps(_TSCONFIG, ensure_ascii=False, indent=2), encoding="utf-8")
    (workdir / "remotion.config.js").write_text("module.exports = {};\n", encoding="utf-8")
    return workdir


async def _remotion_available() -> bool:
    try:
        proc = await asyncio.create_subprocess_exec(
            "npx", "--yes", "remotion", "--version",
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        return proc.returncode == 0
    except Exception:
        return False


async def _render_remotion(workdir: Path, out_path: Path, pages: list[dict]) -> Path:
    """把三页分镜注入工程并调 remotion render，返回产物路径。"""
    total_frames = sum(_page_frames(p) for p in pages)
    props = {
        "pages": pages,
        "durationInFrames": total_frames,
        "fps": FPS,
        "width": W,
        "height": H,
    }
    props_file = workdir / "props.json"
    props_file.write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")

    cmd = [
        "npx", "remotion", "render", "src/Root.tsx", "QAVideo",
        str(out_path), "--codec=h264", "--concurrency=1",
        f"--props={props_file.resolve()}",
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, cwd=str(workdir),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    out, _ = await proc.communicate()
    if proc.returncode != 0 or not out_path.exists():
        raise RuntimeError(
            f"remotion render 失败 (exit {proc.returncode}): "
            f"{out.decode('utf-8', errors='ignore')[-500:]}"
        )
    return out_path


# ================================================================ PIL 渲染

_FONT_CACHE: dict[tuple[int, bool], object] = {}

_REGULAR_FONTS = [
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/PingFang.ttc",
]
_BOLD_FONTS = [
    "C:/Windows/Fonts/msyhbd.ttc",
    "C:/Windows/Fonts/msyh.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "/System/Library/Fonts/PingFang.ttc",
]


def _font(size: int, bold: bool = False):
    from PIL import ImageFont

    key = (size, bold)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    font = None
    for path in (_BOLD_FONTS if bold else _REGULAR_FONTS):
        try:
            font = ImageFont.truetype(path, size)
            break
        except Exception:
            continue
    if font is None:
        font = ImageFont.load_default()
    _FONT_CACHE[key] = font
    return font


def _wrap(draw, text: str, font, max_width: float) -> list[str]:
    """按像素宽度折行（中文逐字、英文按词尽量整体），绝不产生超宽行。"""
    lines: list[str] = []
    for para in str(text or "").split("\n"):
        cur = ""
        for ch in para:
            trial = cur + ch
            if cur and draw.textlength(trial, font=font) > max_width:
                lines.append(cur)
                cur = ch
            else:
                cur = trial
        if cur:
            lines.append(cur)
    return lines or [""]


def _draw_rich_line(draw, x: float, y: float, line: str, font, bold_font, color: str, accent: str) -> float:
    """单行绘制，数字用强调色加粗（关键数字突出），返回结束 x。"""
    for part in _NUM_RE.split(line):
        if not part:
            continue
        is_num = bool(_NUM_RE.fullmatch(part))
        f = bold_font if is_num else font
        draw.text((x, y), part, font=f, fill=accent if is_num else color)
        x += draw.textlength(part, font=f)
    return x


def _pill(draw, x: float, y: float, label: str, tokens: dict) -> float:
    """微标签胶囊（蓝 tint），返回底部 y。"""
    font = _font(13, bold=True)
    w = draw.textlength(label, font=font)
    pad_x, h = 14, 26
    draw.rounded_rectangle(
        [x, y, x + w + pad_x * 2, y + h], radius=h // 2, fill=tokens["tint_blue_bg"]
    )
    draw.text((x + pad_x, y + (h - 13) / 2 - 2), label, font=font, fill=tokens["tint_blue_ink"])
    return y + h


def _draw_question(draw, page: dict, x: float, y: float, max_w: float, tokens: dict) -> None:
    y = _pill(draw, x, y, page.get("label") or "问题检索", tokens) + 30
    font = _font(36, bold=True)
    lh = int(36 * 1.65)
    for line in _wrap(draw, page.get("title", ""), font, max_w):
        draw.text((x, y), line, font=font, fill=tokens["text"])
        y += lh
    draw.text((x, y + 26), page.get("meta", ""), font=_font(14), fill=tokens["text_tertiary"])


def _draw_answer(draw, page: dict, x: float, y: float, max_w: float, tokens: dict) -> None:
    y = _pill(draw, x, y, page.get("label") or "核心解答", tokens) + 18
    # 问题回顾（最多两行，超出以省略号收尾——仅为上下文小字，非答案正文）
    recap_font = _font(14)
    recap_lines = _wrap(draw, page.get("recap", ""), recap_font, max_w)
    if len(recap_lines) > 2:
        recap_lines = recap_lines[:2]
        recap_lines[1] += "…"
    for line in recap_lines:
        draw.text((x, y), line, font=recap_font, fill=tokens["text_tertiary"])
        y += int(14 * 1.65)
    # 核心结论（28px 加粗，数字强调）
    y += 14
    sum_font = _font(28, bold=True)
    sum_bold = _font(28, bold=True)
    for line in _wrap(draw, page.get("summary", ""), sum_font, max_w):
        _draw_rich_line(draw, x, y, line, sum_font, sum_bold, tokens["text"], tokens["accent"])
        y += int(28 * 1.65)
    # 要点（≤3，项目符号 + 数字强调）
    y += 26
    point_font = _font(18)
    point_bold = _font(18, bold=True)
    indent = 22
    for p in (page.get("points") or [])[:3]:
        marker_y = y + int(18 * 0.62)
        draw.ellipse(
            [x, marker_y - 4, x + 8, marker_y + 4], fill=tokens["accent"]
        )
        py = y
        for line in _wrap(draw, p, point_font, max_w - indent):
            _draw_rich_line(draw, x + indent, py, line, point_font, point_bold, tokens["text_secondary"], tokens["accent"])
            py += int(18 * 1.7)
        y = py + 14


def _draw_citations(draw, page: dict, x: float, y: float, max_w: float, tokens: dict) -> None:
    y = _pill(draw, x, y, page.get("label") or "引用参考文档", tokens) + 22
    name_font = _font(15, bold=True)
    path_font = _font(12)
    snip_font = _font(13)
    for card in (page.get("citations") or [])[:3]:
        inner_w = max_w - 36  # 卡片左右内边距 18
        name_lines = _wrap(draw, card.get("source_file", ""), name_font, inner_w)[:1]
        path_lines = _wrap(draw, card.get("heading_path", ""), path_font, inner_w)
        if len(path_lines) > 1:
            path_lines = path_lines[:1]
            path_lines[0] += "…"
        snip_all = _wrap(draw, card.get("snippet", ""), snip_font, inner_w - 24)
        snip_lines = snip_all[:2]
        if len(snip_all) > 2:
            snip_lines[1] = snip_lines[1][:-1] + "…"
        h = 14 + 20 + len(path_lines) * 18 + 8 + 12 + len(snip_lines) * int(13 * 1.6) + 12
        draw.rounded_rectangle([x, y, x + max_w, y + h], radius=8, outline=tokens["border"], fill=tokens["bg"])
        cy = y + 12
        draw.text((x + 18, cy), name_lines[0] if name_lines else "", font=name_font, fill=tokens["text"])
        cy += 22
        for line in path_lines:
            draw.text((x + 18, cy), line, font=path_font, fill=tokens["text_tertiary"])
            cy += 18
        cy += 6
        snip_h = 8 + len(snip_lines) * int(13 * 1.6) + 6
        draw.rounded_rectangle(
            [x + 18, cy, x + max_w - 18, cy + snip_h], radius=6, fill=tokens["bg_subtle"]
        )
        ty = cy + 6
        for line in snip_lines:
            draw.text((x + 30, ty), line, font=snip_font, fill=tokens["text_secondary"])
            ty += int(13 * 1.6)
        y += h + 14


def _page_image(page: dict, idx: int, total: int, tokens: dict):
    """预渲染一页（含顶栏与页脚），供逐帧合成。

    正文先画到透明层、取内容包围盒后按卡片内区垂直居中粘贴：
    内容多则自然靠上填满，内容少也不会"文字漂在空卡片顶部"。
    """
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (W, H), tokens["bg"])
    d = ImageDraw.Draw(img)
    # 顶栏 56px + 1px 描边
    d.rectangle([0, 0, W - 1, 55], outline=tokens["border"], width=1)
    d.text((24, 18), "知识库问答 · 视频工作台", font=_font(16), fill=tokens["text"])
    page_no = f"{idx + 1} / {total}"
    d.text((W - 24 - d.textlength(page_no, font=_font(12)), 20), page_no,
           font=_font(12), fill=tokens["text_tertiary"])
    # 居中主卡片：白底 + 1px 描边 + 12px 圆角 + 48px 内边距
    left, right = int(W * 0.06), int(W * 0.94)
    top, bottom = 88, H - 72
    d.rounded_rectangle([left, top, right, bottom], radius=12, outline=tokens["border"], fill=tokens["bg"])
    pad = 48
    cw = (right - left) - pad * 2
    ch = (bottom - top) - pad * 2
    max_w = cw * 0.88  # 文本容器 max-width 88%

    # 正文绘制在透明层上（尺寸留足余量用于测量）
    layer = Image.new("RGBA", (cw, ch + 240), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    kind = page.get("kind")
    if kind == "question":
        _draw_question(ld, page, 0, 0, max_w, tokens)
    elif kind == "answer":
        _draw_answer(ld, page, 0, 0, max_w, tokens)
    else:
        _draw_citations(ld, page, 0, 0, max_w, tokens)
    bbox = layer.getbbox()
    if bbox:
        content = layer.crop(bbox)
        x = left + pad
        y = top + pad + max(0, (ch - content.height) // 2)
        y = min(y, bottom - pad - content.height) if content.height <= ch else top + pad
        if y < top + pad:
            y = top + pad
        img.paste(content, (x, y), content)

    # 页脚
    d.rectangle([0, H - 49, W - 1, H - 48], outline=tokens["border"], width=1)
    d.text((24, H - 40), "知识库问答 · 自动生成", font=_font(12), fill=tokens["text_tertiary"])
    return img


def _compose_frame(page_imgs, idx: int, local: int, global_frame: int, total_frames: int, tokens: dict):
    """合成单帧：页切换 180ms 淡入 + 8px 微位移；顶部进度条随全局时间轴增长。"""
    from PIL import Image, ImageDraw

    if idx > 0 and local < TRANSITION_FRAMES:
        alpha = (local + 1) / TRANSITION_FRAMES
        cur = page_imgs[idx]
        if local < TRANSITION_FRAMES - 1:
            shift = (TRANSITION_FRAMES - local) * 2  # 8→2px
            shifted = Image.new("RGB", (W, H), tokens["bg"])
            shifted.paste(cur, (0, shift))
            cur = shifted
        frame = Image.blend(page_imgs[idx - 1], cur, alpha)
    else:
        frame = page_imgs[idx].copy()
    d = ImageDraw.Draw(frame)
    progress = (global_frame + 1) / max(total_frames, 1)
    d.rectangle([0, 56, int(W * progress), 58], fill=tokens["accent"])
    return frame


async def _render_pil(pages: list[dict], out_path: Path, tokens: dict, total_frames: int) -> Path:
    """逐帧 PIL 渲染（进度条连续增长、页面淡入），ffmpeg 编码为无声底片。"""
    work = out_path.with_suffix(".parts")
    frames_dir = work / "frames"
    shutil.rmtree(frames_dir, ignore_errors=True)
    frames_dir.mkdir(parents=True, exist_ok=True)

    page_imgs = [_page_image(p, i, len(pages), tokens) for i, p in enumerate(pages)]
    seq = [_page_frames(p) for p in pages]

    f = 0
    for idx in range(len(pages)):
        for local in range(seq[idx]):
            frame = _compose_frame(page_imgs, idx, local, f, total_frames, tokens)
            frame.save(str(frames_dir / f"frame{f:05d}.png"), "PNG")
            f += 1

    await _ffmpeg(
        "-y", "-framerate", str(FPS),
        "-i", str(frames_dir / "frame%05d.png"),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS),
        "-t", f"{total_frames / FPS:.3f}",
        str(out_path),
    )
    return out_path


async def _ffmpeg(*args: str) -> None:
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", *args,
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg 失败 (exit {proc.returncode}): {' '.join(args)}")


# ================================================================ 入口

async def render_pages(
    pages: list[dict], out_path: Path, *, prefer: str = "remotion"
) -> dict:
    """渲染三页分镜为无声 MP4（音轨由 video.py 的 mux 阶段合成）。

    每页时长取 page["frames"]（由逐页 TTS 真实时长换算，见 video.py）；
    prefer='remotion' 时优先 Remotion，不可用自动降级 PIL。
    """
    out_path = Path(str(out_path))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    work = out_path.with_suffix(".parts")
    work.mkdir(parents=True, exist_ok=True)
    tokens = _tokens_from_css()
    total_frames = sum(_page_frames(p) for p in pages)

    engine = "pil"
    if prefer == "remotion" and await _remotion_available():
        try:
            await _render_remotion(work, out_path, pages)
            engine = "remotion"
        except Exception:
            engine = "pil"
    if engine == "pil":
        await _render_pil(pages, out_path, tokens, total_frames)

    return {
        "path": str(out_path),
        "seconds": round(total_frames / FPS, 3),
        "engine": engine,
        "pages": len(pages),
        "frames": total_frames,
    }


# 兼容旧调用名（分镜页即"段"）
render_segments = render_pages
