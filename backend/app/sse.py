"""SSE 事件流（API_SPEC §6）：问答进度 + 视频进度实时推送。"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import Request
from fastapi.responses import StreamingResponse

from .db import get_conn

_subs: set[asyncio.Queue] = set()


async def broadcast(event: str, data: dict[str, Any]) -> None:
    """向所有活跃 SSE 连接广播事件。"""
    for q in list(_subs):
        try:
            q.put_nowait((event, data))
        except Exception:
            pass


def on_video_progress(task_id: int, stage: str, progress: float) -> None:
    """video_queue 回调 → video.progress / video.done / video.failed 事件。

    video.done 携带 API_SPEC §6 要求的 video_url（产物下载路径）；
    video.failed 的 error 为任务失败原因（从 video_tasks.error 读，而非 stage）。
    """
    if stage == "done":
        with get_conn() as conn:
            t = conn.execute(
                "SELECT video_path FROM video_tasks WHERE id = ?", (task_id,)
            ).fetchone()
        video_url = f"/api/videos/{task_id}/file" if t and t["video_path"] else None
        asyncio.get_event_loop().call_soon(
            lambda: asyncio.ensure_future(
                broadcast("video.done", {"task_id": task_id, "progress": 1.0, "video_url": video_url})
            )
        )
    elif stage == "failed":
        with get_conn() as conn:
            t = conn.execute(
                "SELECT error FROM video_tasks WHERE id = ?", (task_id,)
            ).fetchone()
        err = (t and t["error"]) or stage
        asyncio.get_event_loop().call_soon(
            lambda: asyncio.ensure_future(
                broadcast("video.failed", {"task_id": task_id, "error": str(err)})
            )
        )
    else:
        asyncio.get_event_loop().call_soon(
            lambda: asyncio.ensure_future(
                broadcast(
                    "video.progress",
                    {"task_id": task_id, "stage": stage, "progress": round(progress, 4)},
                )
            )
        )


async def event_stream(request: Request):
    """SSE 连接：保持心跳并转发广播事件。"""
    q: asyncio.Queue = asyncio.Queue()
    _subs.add(q)

    async def gen():
        try:
            yield "event: ping\ndata: {}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event, data = await asyncio.wait_for(q.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield "event: ping\ndata: {}\n\n"
                    continue
                yield f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        finally:
            _subs.discard(q)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
