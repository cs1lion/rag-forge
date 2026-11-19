"""视频合成编排（ARCHITECTURE §6：script → tts → render → mux）。

问答视频 = 三页分镜 + 逐页 TTS 配音 + 真实时长驱动切页 + 渲染 + ffmpeg 音画合成。
全部本地真实生成，零 Mock。

音画同步（严格）：
1. 每一页单独合成为独立音频（Page1/Page2/Page3 各一条）；
2. 读取该页音频的精确时长（WAV 帧数 / 采样率，毫秒级），
   末尾追加 0.4s 呼吸停顿缓冲；
3. 以该页时长换算出**帧数**写入分镜（page["frames"]），渲染端按页边界切页；
4. 音频按同样时长补静音对齐（apad + -t），与画面帧数完全一致：
   「第 1 页念完 → 切第 2 页 → 第 2 页念完 → 切第 3 页 → 三页播完才结束」。
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from .config import settings
from .tts import synth
from .video_render import FPS, render_pages
from .video_script import build_video_script

# 视频规格（与 DESIGN.md §5 一致的纸感视觉）
W, H = 1280, 720

# 每页语音结束后的呼吸停顿（秒）
BREATH_PAUSE = 0.4


async def render_qa_video(
    *,
    question: str,
    answer: str,
    citations: list[dict],
    out_path: Path,
    on_progress=None,
) -> dict:
    """合成问答视频。返回 {path, seconds, size, stages, engine, script_method, pages}。"""
    out_path = Path(str(out_path))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    work = out_path.with_suffix(".parts")
    work.mkdir(parents=True, exist_ok=True)

    def report(stage: str, pct: float):
        if on_progress:
            on_progress(stage, min(max(pct, 0.0), 1.0))

    # ---- script：三页分镜（LLM 提炼结论/要点，失败规则降级） -------------
    report("script", 0.02)
    pages, script_method = await build_video_script(question, answer, citations)
    report("script", 0.08)

    # ---- tts：逐页独立配音，真实时长 → 帧数 ------------------------------
    audio_segs: list[Path] = []
    for i, page in enumerate(pages):
        raw = work / f"page{i}.wav"
        info = await synth(page.get("narration", ""), raw)
        frames = max(1, round((float(info["seconds"]) + BREATH_PAUSE) * FPS))
        duration = frames / FPS
        # 该页音频补齐到与画面帧数完全一致的时长（末尾静音即呼吸停顿）
        padded = work / f"page{i}_padded.wav"
        await _ffmpeg(
            "-y", "-i", str(raw),
            "-af", "apad",
            "-t", f"{duration:.3f}",
            "-ac", "1", "-ar", "24000", "-c:a", "pcm_s16le",
            str(padded),
        )
        page["audio"] = str(padded)
        page["seconds"] = round(float(info["seconds"]), 3)
        page["duration"] = round(duration, 3)
        page["frames"] = frames
        audio_segs.append(padded)
        report("tts", 0.08 + 0.32 * (i + 1) / max(len(pages), 1))

    total_frames = sum(p["frames"] for p in pages)
    total_seconds = total_frames / FPS

    # ---- render：按页时长渲染（Remotion / PIL） --------------------------
    report("render", 0.40)
    silent = work / "video_silent.mp4"
    result = await render_pages(pages, silent, prefer="remotion")
    engine = result["engine"]
    report("render", 0.75)

    # ---- mux：逐页音频顺序拼接后与画面合成 ------------------------------
    report("mux", 0.80)
    audio_cat = work / "audio_full.wav"
    # 注意：不能用 concat: 协议——它对 WAV 只会读到第一段，导致音轨被截成
    # 第 1 页时长、再由 -shortest 把画面一并截断（第 3 页未播完的根因）。
    # 改用 concat 解复用器 + 文件清单（同参数 PCM，流拷贝即可）。
    list_file = work / "audio_list.txt"
    list_file.write_text(
        "\n".join(f"file '{a.resolve().as_posix()}'" for a in audio_segs),
        encoding="utf-8",
    )
    await _ffmpeg(
        "-f", "concat", "-safe", "0", "-i", str(list_file),
        "-c", "copy", "-y", str(audio_cat),
    )
    report("mux", 0.92)
    # 成片时长固定为总帧数对应的时长（不用 -shortest：音轨缺尾时会把画面截断）
    await _ffmpeg(
        "-i", str(silent), "-i", str(audio_cat),
        "-c:v", "copy", "-c:a", "aac",
        "-t", f"{total_seconds:.3f}", "-y", str(out_path),
    )
    report("mux", 1.0)

    return {
        "path": str(out_path),
        "seconds": round(total_seconds, 2),
        "size": out_path.stat().st_size,
        "segments": len(pages),
        "pages": len(pages),
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
