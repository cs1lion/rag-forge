"""视频合成编排（ARCHITECTURE §6：script → tts → render → mux）。

问答视频 = 大模型分镜脚本 + edge-tts 逐段配音 + Remotion/HyperFrames 渲染
（复用 design/tokens.css 白底 1px 细边框极简排版）+ ffmpeg 音画合成。
全部本地真实生成，零 Mock。
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from .config import settings
from .tts import synth
from .video_render import render_segments
from .video_script import build_video_script

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
    """合成问答视频。返回 {path, seconds, size, stages, engine, script_method}。

    阶段：
      script  — 大模型提炼结构化分镜（失败降级规则切句）
      tts     — 逐段配音（edge-tts / openai-tts）
      render  — Remotion 渲染（复用 tokens.css；不可用降级 PIL+ffmpeg）
      mux     — ffmpeg 音画合成
    """
    out_path = Path(str(out_path))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    work = out_path.with_suffix(".parts")
    work.mkdir(parents=True, exist_ok=True)

    def report(stage: str, pct: float):
        if on_progress:
            on_progress(stage, min(max(pct, 0.0), 1.0))

    # ---- script：大模型分镜脚本（LLM 优先，规则降级） -------------------
    report("script", 0.02)
    segments, script_method = await build_video_script(question, answer, citations)
    report("script", 0.08)

    # ---- tts：逐段配音 -------------------------------------------------
    audio_segs: list[Path] = []
    for i, seg in enumerate(segments):
        wav = work / f"seg{i:02d}.wav"
        info = await synth(seg["narration"], wav)
        seg["audio"] = str(wav)
        seg["seconds"] = info["seconds"]
        audio_segs.append(wav)
        report("tts", 0.08 + 0.32 * (i + 1) / max(len(segments), 1))

    # ---- render：Remotion / HyperFrames 渲染（复用 tokens.css） ----------
    report("render", 0.40)
    silent = work / "video_silent.mp4"
    result = await render_segments(segments, silent, prefer="remotion")
    engine = result["engine"]
    report("render", 0.75)

    # ---- mux：ffmpeg 音画合成 -------------------------------------------
    report("mux", 0.80)
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
        "engine": engine,
        "script_method": script_method,
    }


async def _ffmpeg(*args: str) -> None:
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", *args,
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg 失败 (exit {proc.returncode}): {' '.join(args)}")
