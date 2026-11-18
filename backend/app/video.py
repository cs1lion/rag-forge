"""视频合成（ARCHITECTURE §6：script → tts → render → mux）。

问答视频 = 标题卡 + 逐段问题/回答字幕 + 背景视觉 + TTS 音轨，
全部本地生成（ffmpeg + PIL），零 Mock。
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from .config import settings
from .tts import synth

# 视频规格（与 DESIGN.md §5 一致的纸感视觉）
W, H = 1280, 720
FPS = 24


async def render_qa_video(
    *,
    question: str,
    answer: str,
    citations: list[dict],
    out_path: Path,
    on_progress=None,
) -> dict:
    """合成问答视频。返回 {path, seconds, size, stages}。

    阶段：
      script  — 分镜脚本（题卡 + 答案分段 + 引用页）
      tts     — 逐段配音（edge-tts / openai-tts）
      render  — 逐段画面（PIL 绘图纸感卡片）
      mux     — ffmpeg 音画合成 + 封面
    """
    out_path = Path(str(out_path))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    work = out_path.with_suffix(".parts")
    work.mkdir(parents=True, exist_ok=True)

    def report(stage: str, pct: float):
        if on_progress:
            on_progress(stage, min(max(pct, 0.0), 1.0))

    # ---- script：分镜脚本 --------------------------------------------
    report("script", 0.02)
    segments = _build_script(question, answer, citations)
    report("script", 0.08)

    # ---- tts：逐段配音 ------------------------------------------------
    audio_segs: list[Path] = []
    for i, seg in enumerate(segments):
        wav = work / f"seg{i:02d}.wav"
        info = await synth(seg["narration"], wav)
        seg["audio"] = str(wav)
        seg["seconds"] = info["seconds"]
        audio_segs.append(wav)
        report("tts", 0.08 + 0.32 * (i + 1) / len(segments))

    # ---- render：逐段画面 ----------------------------------------------
    img_segs: list[Path] = []
    for i, seg in enumerate(segments):
        png = work / f"seg{i:02d}.png"
        _draw_segment(png, seg, i, len(segments))
        img_segs.append(png)
        report("render", 0.40 + 0.35 * (i + 1) / len(segments))

    # ---- mux：ffmpeg 音画合成 ------------------------------------------
    report("mux", 0.76)
    list_file = work / "segments.txt"
    list_file.write_text(
        "".join(f"file '{p.name}'\n" for p in img_segs), encoding="utf-8"
    )
    silent = work / "video_silent.mp4"
    await _ffmpeg(
        "-f", "concat", "-safe", "0", "-i", str(list_file),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS),
        "-y", str(silent),
    )
    report("mux", 0.84)
    audio_cat = work / "audio_full.wav"
    await _ffmpeg(
        "-i", f"concat:{'|'.join(str(a) for a in audio_segs)}",
        "-c", "copy", "-y", str(audio_cat),
    )
    report("mux", 0.92)
    await _ffmpeg(
        "-i", str(silent), "-i", str(audio_cat),
        "-c:v", "copy", "-c:a", "aac", "-shortest", "-y", str(out_path),
    )
    report("mux", 1.0)

    seconds = sum(s.get("seconds", 0) for s in segments)
    return {
        "path": str(out_path),
        "seconds": round(seconds, 2),
        "size": out_path.stat().st_size,
        "segments": len(segments),
        "stages": ["script", "tts", "render", "mux"],
    }


# ---------------------------------------------------------------- 分镜


def _build_script(question: str, answer: str, citations: list[dict]) -> list[dict]:
    """把问答拆成分镜段：题卡 → 答案逐句 → 引用页。"""
    segs: list[dict] = []
    segs.append({
        "kind": "title",
        "title": question,
        "subtitle": "知识库问答 · 引用溯源见片尾",
        "narration": f"问题是：{question}",
    })
    # 答案按句号/分号切句，每句一段（控制单段时长，利于字幕同步）
    sentences = _split_sentences(answer)
    for s in sentences:
        segs.append({"kind": "body", "title": s, "subtitle": "", "narration": s})
    if citations:
        cite_lines = [
            f"{c.get('source_file', c.get('doc_id', ''))} · {c.get('heading_path', '')}"
            for c in citations
        ]
        segs.append({
            "kind": "citations",
            "title": "引用参考",
            "subtitle": " · ".join(cite_lines) or "无",
            "narration": f"以上回答引用了 {len(citations)} 个知识库段落。",
        })
    return segs


def _split_sentences(text: str) -> list[str]:
    import re

    parts = re.split(r"(?<=[。！？；])\s*", text.strip())
    parts = [p for p in parts if p]
    if not parts:
        return [text.strip() or "（无内容）"]
    # 过长的句子按逗号再切，限制单段 ≤ 60 字
    out = []
    for p in parts:
        while len(p) > 60:
            cut = p.find("，", 30, 60)
            if cut == -1:
                cut = 60
            out.append(p[: cut + 1])
            p = p[cut + 1:]
        out.append(p)
    return out


# ---------------------------------------------------------------- 画面


def _draw_segment(png: Path, seg: dict, idx: int, total: int):
    """用 PIL 绘图纸感画面：白底、1px 描边、层级靠留白与细线。"""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (W, H), "#FFFFFF")
    d = ImageDraw.Draw(img)

    # 顶栏：56px + 1px 描边
    d.rectangle([0, 0, W - 1, 55], outline="#E1E3E6", width=1)
    d.text((24, 18), "知识库问答 · 视频工作台", fill="#1F1F1F")
    d.text((W - 160, 18), f"{idx + 1} / {total}", fill="#5E5E5E")

    # 页码进度线（琥珀色墨线）
    d.rectangle([0, 55, int(W * (idx + 1) / max(total, 1)), 57], fill="#C98A2C")

    kind = seg.get("kind", "body")
    if kind == "title":
        _wrap_text(d, seg["title"], 60, 200, 40, "#1F1F1F", bold=True)
        if seg.get("subtitle"):
            _wrap_text(d, seg["subtitle"], 60, 300, 20, "#5E5E5E")
    elif kind == "citations":
        _wrap_text(d, seg["title"], 60, 200, 28, "#1F1F1F", bold=True)
        _wrap_text(d, seg.get("subtitle", ""), 60, 260, 18, "#444746")
    else:
        _wrap_text(d, seg["title"], 80, 220, 26, "#1F1F1F")

    # 底部 1px 分隔线 + 元信息
    d.rectangle([0, H - 49, W - 1, H - 48], outline="#E1E3E6", width=1)
    d.text((24, H - 40), f"段 {idx + 1}/{total} · 自动生成", fill="#5E5E5E")

    img.save(str(png), "PNG")


def _wrap_text(d, text: str, x: int, y: int, size: int, fill: str, *, bold: bool = False):
    """按宽度自动换行绘制（中文逐字度量）。"""
    from PIL import ImageFont

    try:
        font = ImageFont.truetype(
            "C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc", size
        )
    except Exception:
        font = ImageFont.load_default()
    max_w = W - 2 * x
    line = ""
    for ch in text:
        if d.textlength(line + ch, font=font) > max_w and line:
            d.text((x, y), line, font=font, fill=fill)
            y += int(size * 1.65)
            line = ch
        else:
            line += ch
    if line:
        d.text((x, y), line, font=font, fill=fill)


# ---------------------------------------------------------------- ffmpeg


async def _ffmpeg(*args: str) -> None:
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", *args,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg 失败 (exit {proc.returncode}): {' '.join(args)}")
