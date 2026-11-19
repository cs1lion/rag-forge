"""全局单并发视频合成队列（ARCHITECTURE §6 / CLAUDE.md 铁律 2）。

- 同一时刻 running ≤ 1：由 asyncio.Lock + DB 状态双保险；
- FIFO：queued 按 created_at 提升；
- 启动恢复：残留 running → queued，所有 queued 按 created_at 升序重建内存队列，
  防止服务重启导致任务永久卡死；
- 拒答跳过：知识库未命中时不进入耗时合成，任务直接标记 skipped；
- SSE 进度经 on_progress 回调推送（qa.progress / video.progress）。
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from .db import get_conn
from .video import render_qa_video

# 拒答跳过视频生成时的说明（写入 video_tasks.stage_text）
SKIP_STAGE_TEXT = "知识库未命中，已跳过视频生成"

_lock: asyncio.Lock | None = None
# 内存队列：启动恢复与新增任务都会推入 task_id。
# DB 仍是唯一事实源；该队列用于"有任务待处理"的唤醒信号与重启后重建可见性。
_pending: asyncio.Queue[int] | None = None


def video_lock() -> asyncio.Lock:
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


def pending_queue() -> asyncio.Queue[int]:
    """全局内存待处理队列（懒创建；同一进程内单例）。"""
    global _pending
    if _pending is None:
        _pending = asyncio.Queue()
    return _pending


def reset_pending_queue() -> None:
    """重置内存队列（测试隔离用）。"""
    global _pending
    _pending = None


def _push_pending(task_id: int) -> None:
    # put_nowait 不需要事件循环绑定，跨测试/跨循环安全
    pending_queue().put_nowait(task_id)


def drain_pending() -> list[int]:
    """取出当前内存队列中的全部 task_id（调度器作为唤醒信号消费）。"""
    q = pending_queue()
    ids: list[int] = []
    while True:
        try:
            ids.append(q.get_nowait())
        except asyncio.QueueEmpty:
            break
    return ids


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
    _push_pending(task_id)
    return get_task(conn, task_id)


async def enqueue_skipped(
    conn, qa_record_id: int, stage_text: str = SKIP_STAGE_TEXT
) -> dict:
    """拒答时创建 skipped 任务：不进入合成队列、不占用单并发名额。"""
    now = _utcnow()
    cur = conn.execute(
        "INSERT INTO video_tasks (qa_record_id, status, progress, stage, stage_text,"
        " created_at, finished_at) VALUES (?, 'skipped', 0.0, 'skipped', ?, ?, ?)",
        (qa_record_id, stage_text, now, now),
    )
    conn.commit()
    return get_task(conn, cur.lastrowid)


def restore_queue(conn) -> list[int]:
    """服务启动恢复：running → queued，并按 created_at 升序重建内存队列。

    返回重新入队的 task_id 列表（按 FIFO 顺序）。
    """
    conn.execute(
        "UPDATE video_tasks SET status='queued', progress=0.0, stage='',"
        " stage_text=NULL, started_at=NULL WHERE status='running'"
    )
    conn.commit()
    rows = conn.execute(
        "SELECT id FROM video_tasks WHERE status='queued' ORDER BY created_at, id"
    ).fetchall()
    ids = [r["id"] for r in rows]
    for tid in ids:
        _push_pending(tid)
    return ids


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
            # 内存队列仅作唤醒信号；任务取自 DB（唯一事实源），避免重复处理
            drain_pending()
            await asyncio.sleep(0.5)
            with get_conn() as conn:
                task = conn.execute(
                    "SELECT * FROM video_tasks WHERE status = 'queued'"
                    " ORDER BY created_at, id LIMIT 1"
                ).fetchone()
                if task is None:
                    continue
                conn.execute(
                    "UPDATE video_tasks SET status='running', started_at=?, progress=0.0,"
                    " stage='' WHERE id=?",
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
            # 铁律 2 双保险：asyncio.Lock（全局单并发）+ DB running 状态约束。
            # 锁内完成整个合成任务，物理层面同一时刻活跃视频任务数 ≤ 1。
            async with video_lock():
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
