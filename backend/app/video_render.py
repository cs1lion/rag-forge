"""Remotion / HyperFrames 视频渲染（CLAUDE.md 视频技术栈更新）。

把分镜段序列渲染为 MP4：
- 生成一次性 Remotion 工程（backend/video_render/），React 组件样式值
  **逐字取自 design/tokens.css**（白底、1px 细边框、编辑型排版）；
- 调 `npx remotion render` 合成 MP4（Chrome headless，真实渲染，零 Mock）；
- Remotion 不可用（缺 Node/Chrome/依赖）时降级为 PIL+ffmpeg 兜底，
  兜底同样复用 tokens.css 的色板/字号/间距，保证产物真实落盘。

契约：render_segments(segments, out_path) -> dict{path, seconds, engine}
"""
from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path

from .config import settings

# 视频规格（与 DESIGN.md 编辑型工作台一致：白底 + 1px 描边）
W, H = 1280, 720
FPS = 24

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
    "radius_md": 12,
    "space_16": 16,
    "space_24": 24,
    "space_32": 32,
    "font_sans": '"Noto Sans SC","PingFang SC","Microsoft YaHei",system-ui,sans-serif',
}


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
    import re

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
        "--nb-radius-md": "radius_md",
    }
    for var, key in mapping.items():
        m = re.search(rf"{re.escape(var)}:\s*([^;]+);", css)
        if m:
            out[key] = m.group(1).strip()
    return out


# ---------------------------------------------------------------- Remotion 工程

_ROOT_TSX = '''\
import React from "react";
import { Composition } from "remotion";
import { QAVideo } from "./QAVideo";

export const RemotionRoot: React.FC = () => {
  const props = (globalThis as any).__QA_PROPS__ as any;
  return (
    <Composition
      id="QAVideo"
      component={QAVideo}
      durationInFrames={props.durationInFrames}
      fps={props.fps}
      width={props.width}
      height={props.height}
      defaultProps={{ segments: props.segments, W: props.width, H: props.height }}
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
};
const FONT = "__FONT__";

const wrap = (text: string, max: number) => {
  const lines: string[] = [];
  let cur = "";
  for (const ch of text) {
    if (cur.length >= max) { lines.push(cur); cur = ch; }
    else cur += ch;
  }
  if (cur) lines.push(cur);
  return lines;
};

export const QAVideo: React.FC<{ segments: any[]; W?: number; H?: number }> = (props) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const segs = props.segments || [];
  const per = 4 * fps; // 每段 4 秒
  const idx = Math.min(Math.floor(frame / per), Math.max(segs.length - 1, 0));
  const local = frame - idx * per;
  const s = segs[idx] || { kind: "body", title: "", subtitle: "", narration: "" };

  const fade = interpolate(local, [0, 12], [0, 1], {
    easing: Easing.out(Easing.cubic),
    extrapolateRight: "clamp",
  });

  const titleSize = s.kind === "title" ? 44 : 30;
  const lines = wrap(s.title || "", s.kind === "title" ? 18 : 26);

  return (
    <AbsoluteFill style={{ background: C.bg, fontFamily: FONT }}>
      {/* 顶栏：56px + 1px 描边 */}
      <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: 56,
        borderBottom: `1px solid ${C.border}`, display: "flex", alignItems: "center",
        justifyContent: "space-between", paddingLeft: 24, paddingRight: 24 }}>
        <span style={{ fontSize: 16, fontWeight: 500, color: C.text }}>知识库问答 · 视频工作台</span>
        <span style={{ fontSize: 12, color: C.tertiary }}>{idx + 1} / {segs.length}</span>
      </div>
      {/* 琥珀色进度墨线 */}
      <div style={{ position: "absolute", top: 56, left: 0, height: 2,
        width: `${((idx + Math.min(local / per, 1)) / Math.max(segs.length, 1)) * 100}%`, background: "#C98A2C" }} />
      {/* 主内容卡：白底 + 1px 描边 + 12px 圆角 */}
      <div style={{ position: "absolute", left: 64, right: 64, top: 120, bottom: 120,
        border: `1px solid ${C.border}`, borderRadius: 12, padding: 40,
        opacity: fade, display: "flex", flexDirection: "column", justifyContent: "center" }}>
        {s.kind === "title" && (
          <div style={{ fontSize: 11, fontWeight: 500, letterSpacing: "0.02em",
            color: C.tertiary, marginBottom: 16 }}>QUESTION</div>
        )}
        {s.kind === "citations" && (
          <div style={{ fontSize: 11, fontWeight: 500, letterSpacing: "0.02em",
            color: C.tertiary, marginBottom: 16 }}>CITATIONS</div>
        )}
        {lines.map((ln, i) => (
          <div key={i} style={{ fontSize: titleSize, lineHeight: 1.65, fontWeight: s.kind === "title" ? 500 : 400,
            color: s.kind === "body" ? C.secondary : C.text }}>{ln}</div>
        ))}
        {s.subtitle && (
          <div style={{ fontSize: 14, lineHeight: 1.65, color: C.secondary, marginTop: 20,
            maxHeight: 160, overflow: "hidden" }}>{wrap(s.subtitle, 40).map((l, i) => <div key={i}>{l}</div>)}</div>
        )}
      </div>
      {/* 底部 1px 分隔线 + 元信息 */}
      <div style={{ position: "absolute", left: 0, right: 0, bottom: 48, height: 1, background: C.border }} />
      <div style={{ position: "absolute", left: 24, bottom: 16, fontSize: 12, color: C.tertiary }}>
        段 {idx + 1}/{segs.length} · 自动生成
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
    """生成（并安装依赖）一次性 Remotion 工程，返回工程根。"""
    src = workdir / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "QAVideo.tsx").write_text(
        _QA_TSX.replace("__BG__", tokens["bg"])
        .replace("__BG_SUBTLE__", tokens["bg_subtle"])
        .replace("__BORDER__", tokens["border"])
        .replace("__TEXT__", tokens["text"])
        .replace("__TEXT_SECONDARY__", tokens["text_secondary"])
        .replace("__TEXT_TERTIARY__", tokens["text_tertiary"])
        .replace("__ACCENT__", tokens["accent"])
        .replace("__ACCENT_SOFT__", tokens["accent_soft"])
        .replace("__FONT__", tokens["font_sans"]),
        encoding="utf-8",
    )
    (src / "Root.tsx").write_text(_ROOT_TSX, encoding="utf-8")
    (workdir / "package.json").write_text(json.dumps(_PKG_JSON, ensure_ascii=False, indent=2), encoding="utf-8")
    (workdir / "tsconfig.json").write_text(json.dumps(_TSCONFIG, ensure_ascii=False, indent=2), encoding="utf-8")
    (workdir / "remotion.config.js").write_text(
        "module.exports = {};\n", encoding="utf-8"
    )
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


async def _render_remotion(
    workdir: Path, out_path: Path, segments: list[dict]
) -> Path:
    """把分镜段注入工程并调 remotion render，返回产物路径。

    Remotion 4 标准注入：CLI --props 传 JSON（含 segments/时长/尺寸），
    入口用 getInputProps() 读取；避免命令行超长与全局变量 hack。
    """
    per_sec = 4
    total_frames = per_sec * FPS * len(segments)
    props = {
        "segments": segments,
        "durationInFrames": total_frames,
        "fps": FPS,
        "width": W,
        "height": H,
    }
    props_file = workdir / "props.json"
    props_file.write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")

    # 入口：Root.tsx 用 getInputProps 读取 CLI --props 注入的值
    root = (workdir / "src" / "Root.tsx").read_text(encoding="utf-8")
    root = root.replace(
        "const props = (globalThis as any).__QA_PROPS__ as any;",
        "import { getInputProps } from \"remotion\";\nconst props = getInputProps() as any;",
    )
    (workdir / "src" / "Root.tsx").write_text(root, encoding="utf-8")

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


# ---------------------------------------------------------------- PIL 兜底

def _draw_pil_segment(png: Path, seg: dict, idx: int, total: int, tokens: dict):
    """兜底渲染：PIL 绘图纸感卡片（同样取 tokens.css 色板）。"""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (W, H), tokens["bg"])
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W - 1, 55], outline=tokens["border"], width=1)
    try:
        f16 = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 16)
        f12 = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 12)
        f26 = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 26)
    except Exception:
        f16 = f12 = f26 = ImageFont.load_default()
    d.text((24, 18), "知识库问答 · 视频工作台", fill=tokens["text"], font=f16)
    d.text((W - 160, 18), f"{idx + 1} / {total}", fill=tokens["text_tertiary"], font=f12)
    d.rectangle([0, 55, int(W * (idx + 1) / max(total, 1)), 57], fill="#C98A2C")
    kind = seg.get("kind", "body")
    title = seg.get("title", "")
    y = 200 if kind != "title" else 180
    d.text((60, y), title, fill=tokens["text"] if kind != "body" else tokens["text_secondary"], font=f26)
    if seg.get("subtitle"):
        d.text((60, y + 80), seg["subtitle"][:60], fill=tokens["text_secondary"], font=f16)
    d.rectangle([0, H - 49, W - 1, H - 48], outline=tokens["border"], width=1)
    d.text((24, H - 40), f"段 {idx + 1}/{total} · 自动生成", fill=tokens["text_tertiary"], font=f12)
    img.save(str(png), "PNG")


async def _render_pil(
    workdir: Path, out_path: Path, segments: list[dict], tokens: dict
) -> Path:
    """兜底：逐段 PNG + ffmpeg concat 协议成 MP4（无 Remotion 时保证产物落盘）。

    Windows 上 ffmpeg concat 解复用器对单引号包裹的相对路径支持不稳定，
    故改用 glob 序列 + concat 协议（无列表文件、路径原生），Windows/Linux 通用。
    """
    img_dir = workdir / "frames"
    img_dir.mkdir(parents=True, exist_ok=True)
    pngs = []
    for i, s in enumerate(segments):
        png = img_dir / f"seg{i:02d}.png"
        _draw_pil_segment(png, s, i, len(segments), tokens)
        pngs.append(png)
    silent = workdir / "silent.mp4"
    # image2 demuxer + glob 通配（Windows 下 concat: 协议对多文件支持不稳定）：
    # frames/segNN.png 按字典序即分镜顺序；输入帧率 1/4 = 每段静态画面停留 4 秒，
    # 输出 -r 24 复制帧到标准 FPS，总时长 = 4s × 段数。
    await _ffmpeg(
        "-f", "image2", "-framerate", "1/4",
        "-i", str(img_dir / "seg%02d.png"),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS),
        "-y", str(silent),
    )
    return silent


async def _ffmpeg(*args: str) -> None:
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", *args,
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg 失败 (exit {proc.returncode}): {' '.join(args)}")


# ---------------------------------------------------------------- 入口

async def render_segments(
    segments: list[dict], out_path: Path, *, prefer: str = "remotion"
) -> dict:
    """渲染分镜段为 MP4。返回 {path, seconds, engine}。

    prefer='remotion' 时优先 Remotion；不可用自动降级 PIL+ffmpeg。
    """
    out_path = Path(str(out_path))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    work = out_path.with_suffix(".parts")
    work.mkdir(parents=True, exist_ok=True)
    tokens = _tokens_from_css()

    engine = "pil"
    if prefer == "remotion" and await _remotion_available():
        try:
            await _render_remotion(work, out_path, segments)
            engine = "remotion"
        except Exception:
            engine = "pil"
    if engine == "pil":
        silent = await _render_pil(work, out_path, segments, tokens)
        # _render_pil 产出 silent.mp4（无声底片）；render_segments 的契约要求 out_path
        # 即最终产物路径，故把底片落盘到 out_path（音画由 video.py 的 mux 阶段完成）。
        if silent != out_path and silent.exists():
            import shutil as _shutil
            _shutil.copyfile(silent, out_path)

    return {
        "path": str(out_path),
        "seconds": 4 * len(segments),
        "engine": engine,
        "segments": len(segments),
    }
