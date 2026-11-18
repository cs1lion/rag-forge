"""TTS 抽象层（ARCHITECTURE §6 视频管线 stage=tts）。

双供应商：
- edge-tts：免费、无需 Key，默认；声音由 EDGE_TTS_VOICE 指定
  （缺省 zh-CN-XiaoxiaoNeural 中文女声）
- openai：OPENAI_TTS_API_KEY + OPENAI_TTS_VOICE（缺省 alloy）

统一产出 24kHz/mono PCM WAV，供 ffmpeg 合成。
"""
from __future__ import annotations

import asyncio
import wave
from pathlib import Path

from .config import settings


class TTSError(RuntimeError):
    """TTS 合成失败（含无可用供应商）。"""


def _probe_wav(path: Path) -> tuple[int, int]:
    """返回 (采样率, 声道数)。"""
    with wave.open(str(path), "rb") as w:
        return w.getframerate(), w.getnchannels()


async def synth(text: str, out_wav: Path, *, voice: str | None = None) -> dict:
    """把文本合成为 WAV。返回 {format, voice, seconds, bytes}。

    edge-tts 路径用 asyncio.create_subprocess_exec，避免同步阻塞事件循环。
    """
    out_wav = Path(str(out_wav))
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    text = (text or "").strip()
    if not text:
        raise TTSError("TTS 输入为空")

    provider = settings.tts_provider or "edge-tts"

    if provider == "edge-tts":
        import edge_tts

        v = voice or settings.edge_tts_voice or "zh-CN-XiaoxiaoNeural"
        communicate = edge_tts.Communicate(text, voice=v)
        await communicate.save(str(out_wav))
        fmt = "edge-tts"
    elif provider == "openai":
        if not settings.openai_tts_api_key:
            raise TTSError("TTS_PROVIDER=openai 但 OPENAI_TTS_API_KEY 为空")
        from openai import OpenAI

        v = voice or settings.openai_tts_voice or "alloy"
        client = OpenAI(api_key=settings.openai_tts_api_key)
        with client.audio.speech.with_streaming_response.create(
            model="tts-1", voice=v, input=text
        ) as resp:
            out_wav.write_bytes(resp.read())
        fmt = "openai-tts"
    else:
        raise TTSError(f"未知 TTS_PROVIDER: {provider}")

    # 统一转 24kHz mono WAV（ffmpeg）
    unified = out_wav.with_suffix(".24k.wav")
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", "-i", str(out_wav),
        "-ac", "1", "-ar", "24000", "-c:a", "pcm_s16le", str(unified),
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.wait()
    if proc.returncode != 0 or not unified.exists():
        unified = out_wav  # 兜底：源文件已是 WAV 时直接用
    unified.replace(out_wav) if unified != out_wav else None

    sr, ch = _probe_wav(out_wav)
    seconds = _wav_seconds(out_wav)
    return {
        "format": fmt,
        "voice": v if provider != "edge-tts" else (voice or settings.edge_tts_voice),
        "sample_rate": sr,
        "channels": ch,
        "seconds": round(seconds, 2),
        "bytes": out_wav.stat().st_size,
    }


def _wav_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / max(w.getframerate(), 1)
