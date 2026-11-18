"""全局单并发视频合成队列（ARCHITECTURE §6 / CLAUDE.md 铁律 2）。

- 同一时刻 running ≤ 1：由 asyncio.Lock + DB 状态双保险；
- FIFO：queued 按 created_at 提升；
- SSE 进度经 on_progress 回调推送（qa.progress / video.progress）。
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from .db import get_conn
from .video import render_qa_video

_lock: asyncio.Lock | None = None


def video_lock() -> asyncio.Lock:
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


async def enqueue_video(conn, qa_record_id: int) -> dict:
    """把视频任务加入队列（queued），返回任务行。不立即执行。"""
    cur = conn.execute(
        "INSERT INTO video_tasks (qa_record_id, status, progress, created_at)"
        " VALUES (?, 'queued', 0.0, ?)",
        (qa_record_id, _utcnow()),
    )
    conn.commit()
    task_id = cur.lastrowid
    return get_task(conn, task_id)


def get_task(conn, task_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM video_tasks WHERE id = ?", (task_id,)).fetchone()
    return dict(row) if row else None


def running_count(conn) -> int:
    return conn.execute(
        "SELECT COUNT(*) AS n FROM video_tasks WHERE status = 'running'"
    ).fetchone()["n"]


def queued_tasks(conn) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM video_tasks WHERE status = 'queued' ORDER BY created_at, id"
    ).fetchall()
    return [dict(r) for r in rows]


async def run_dispatcher(app, on_progress) -> None:
    """后台调度：取 queued → 持锁合成 → 更新状态。永不停止（lifespan 内运行）。

    on_progress(task_id, stage, progress) 由调用方（SSE 广播）提供。
    """
    while True:
        try:
            await asyncio.sleep(0.5)
            with get_conn() as conn:
                task = conn.execute(
                    "SELECT * FROM video_tasks WHERE status = 'queued'"
                    " ORDER BY created_at, id LIMIT 1"
                ).fetchone()
                if task is None:
                    continue
                conn.execute(
                    "UPDATE video_tasks SET status='running', started_at=?, progress=0.0"
                    " WHERE id=?",
                    (_utcnow(), task["id"]),
                )
                conn.commit()
            qa = None
            with get_conn() as conn:
                qa = conn.execute(
                    "SELECT * FROM qa_records WHERE id = ?", (task["qa_record_id"],)
                ).fetchone()
            if qa is None:
                with get_conn() as conn:
                    conn.execute(
                        "UPDATE video_tasks SET status='failed', error=? WHERE id=?",
                        ("qa_record 不存在", task["id"]),
                    )
                    conn.commit()
                continue
            try:
                out = app.state.video_dir / f"qa_{task['qa_record_id']}_t{task['id']}.mp4"
                citations = json.loads(qa["citations"] or "[]")

                def prog(stage, pct):
                    with get_conn() as conn:
                        conn.execute(
                            "UPDATE video_tasks SET progress=?, stage=? WHERE id=?",
                            (round(pct, 4), stage, task["id"]),
                        )
                        conn.commit()
                    on_progress(task["id"], stage, pct)

                result = await render_qa_video(
                    question=qa["question"],
                    answer=json.loads(qa["answer"]).get("answer", ""),
                    citations=citations,
                    out_path=out,
                    on_progress=prog,
                )
                with get_conn() as conn:
                    conn.execute(
                        "UPDATE video_tasks SET status='done', progress=1.0,"
                        " video_path=?, finished_at=? WHERE id=?",
                        (str(out), _utcnow(), task["id"]),
                    )
                    conn.commit()
                on_progress(task["id"], "done", 1.0)
            except Exception as e:
                with get_conn() as conn:
                    conn.execute(
                        "UPDATE video_tasks SET status='failed', error=?,"
                        " finished_at=? WHERE id=?",
                        (str(e), _utcnow(), task["id"]),
                    )
                    conn.commit()
                on_progress(task["id"], "failed", 1.0)
        except Exception:
            # 调度器自身异常不退出循环
            await asyncio.sleep(1)
