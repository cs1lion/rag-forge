"""全局单并发视频合成队列 (ARCHITECTURE §6 / CLAUDE.md 铁律 2)。

- 同一时刻 running ≤ 1：由 asyncio.Lock + DB 状态双保险；
- FIFO：queued 按 created_at 提升；
- 启动恢复：残留 running → queued，所有 queued 按 created_at 升序重建内存队列，
  防止服务重启导致任务永久卡死；
- 拒答跳过：知识库未命中时不进入耗时合成，任务直接标记 skipped；
- P0 高可用加固：
  1. 单任务超时熔断（asyncio.wait_for + settings.video_task_timeout_seconds），
     防止 ffmpeg / edge-tts 卡死拖垮整个单并发队列；
  2. 有限次重试（attempt_count <= settings.video_task_max_retries），超限落盘 failed；
  3. 协作式任务取消（cancel_video_task）：支持 queued 秒级取消与 running 中断落盘 cancelled。
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from .config import settings
from .db import get_conn
from .video import render_qa_video

# 拒答跳过视频生成时的说明（写入 video_tasks.stage_text）
SKIP_STAGE_TEXT = "知识库未命中，已跳过视频生成"
CANCEL_STAGE_TEXT = "用户已取消视频生成"

_lock: asyncio.Lock | None = None
_pending: asyncio.Queue[int] | None = None
# 当前正在执行的渲染协程句柄（用于 running 状态下的协作式取消）
_active_tasks: dict[int, asyncio.Task] = {}


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
    """重置内存队列与活跃任务句柄（测试隔离用）。"""
    global _pending
    _pending = None
    _active_tasks.clear()


def _push_pending(task_id: int) -> None:
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
    """把视频任务加入队列 (queued)，返回任务行。不立即执行。"""
    cur = conn.execute(
        "INSERT INTO video_tasks (qa_record_id, status, progress, attempt_count,"
        " cancel_requested, created_at) VALUES (?, 'queued', 0.0, 0, 0, ?)",
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


def cancel_video_task(
    conn, task_id: int, stage_text: str = CANCEL_STAGE_TEXT
) -> dict | None:
    """取消指定视频任务（支持 queued 与 running，终态任务幂等返回）。"""
    task = get_task(conn, task_id)
    if task is None:
        return None
    status = task["status"]
    if status in ("done", "failed", "skipped", "cancelled"):
        return task
    if status == "queued":
        now = _utcnow()
        conn.execute(
            "UPDATE video_tasks SET status='cancelled', stage='cancelled',"
            " stage_text=?, cancel_requested=1, finished_at=? WHERE id=?",
            (stage_text, now, task_id),
        )
        conn.commit()
        return get_task(conn, task_id)
    # status == 'running'：写取消标记并通知正在运行的渲染协程中断
    conn.execute(
        "UPDATE video_tasks SET cancel_requested=1, stage_text=? WHERE id=?",
        (stage_text, task_id),
    )
    conn.commit()
    active = _active_tasks.get(task_id)
    if active is not None and not active.done():
        active.cancel()
    return get_task(conn, task_id)


def restore_queue(conn) -> list[int]:
    """服务启动恢复：running → queued，并按 created_at 升序重建内存队列。"""
    conn.execute(
        "UPDATE video_tasks SET status='queued', progress=0.0, stage='',"
        " stage_text=NULL, cancel_requested=0, started_at=NULL WHERE status='running'"
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


def _is_cancel_requested(conn, task_id: int) -> bool:
    row = conn.execute(
        "SELECT cancel_requested, status FROM video_tasks WHERE id = ?", (task_id,)
    ).fetchone()
    if row is None:
        return True
    return bool(row["cancel_requested"]) or row["status"] == "cancelled"


async def process_one_task(
    app,
    on_progress,
    *,
    db_path=None,
    timeout_seconds: float | None = None,
    max_retries: int | None = None,
) -> bool:
    """执行队列中的下一条 queued 任务（返回 True 表示处理了任务，False 表示队列为空）。

    拆出单步执行函数便于单元测试直接覆盖超时熔断、有限次重试与协作式取消。
    """
    with get_conn(db_path) as conn:
        task = conn.execute(
            "SELECT * FROM video_tasks WHERE status = 'queued'"
            " ORDER BY created_at, id LIMIT 1"
        ).fetchone()
        if task is None:
            return False
        attempt = int(task["attempt_count"] or 0) + 1
        conn.execute(
            "UPDATE video_tasks SET status='running', started_at=?, progress=0.0,"
            " stage='', attempt_count=? WHERE id=?",
            (_utcnow(), attempt, task["id"]),
        )
        conn.commit()

    task_id = task["id"]
    with get_conn(db_path) as conn:
        qa = conn.execute(
            "SELECT * FROM qa_records WHERE id = ?", (task["qa_record_id"],)
        ).fetchone()
    if qa is None:
        with get_conn(db_path) as conn:
            conn.execute(
                "UPDATE video_tasks SET status='failed', error=?, finished_at=? WHERE id=?",
                ("qa_record 不存在", _utcnow(), task_id),
            )
            conn.commit()
        on_progress(task_id, "failed", 1.0)
        return True

    timeout = (
        float(timeout_seconds)
        if timeout_seconds is not None
        else float(getattr(settings, "video_task_timeout_seconds", 180))
    )
    retry_limit = (
        int(max_retries)
        if max_retries is not None
        else int(getattr(settings, "video_task_max_retries", 1))
    )

    # 铁律 2 双保险：asyncio.Lock (全局单并发) + DB running 状态约束。
    async with video_lock():
        out = app.state.video_dir / f"qa_{task['qa_record_id']}_t{task_id}.mp4"
        citations = json.loads(qa["citations"] or "[]")

        def prog(stage, pct):
            with get_conn(db_path) as conn:
                if _is_cancel_requested(conn, task_id):
                    return
                conn.execute(
                    "UPDATE video_tasks SET progress=?, stage=? WHERE id=?",
                    (round(pct, 4), stage, task_id),
                )
                conn.commit()
            on_progress(task_id, stage, pct)

        render_coro = render_qa_video(
            question=qa["question"],
            answer=json.loads(qa["answer"]).get("answer", ""),
            citations=citations,
            out_path=out,
            on_progress=prog,
        )
        render_task = asyncio.create_task(render_coro)
        _active_tasks[task_id] = render_task
        try:
            await asyncio.wait_for(render_task, timeout=timeout)
            with get_conn(db_path) as conn:
                if _is_cancel_requested(conn, task_id):
                    conn.execute(
                        "UPDATE video_tasks SET status='cancelled', stage='cancelled',"
                        " stage_text=?, finished_at=? WHERE id=?",
                        (CANCEL_STAGE_TEXT, _utcnow(), task_id),
                    )
                    conn.commit()
                    on_progress(task_id, "cancelled", 1.0)
                else:
                    conn.execute(
                        "UPDATE video_tasks SET status='done', progress=1.0,"
                        " video_path=?, error=NULL, finished_at=? WHERE id=?",
                        (str(out), _utcnow(), task_id),
                    )
                    conn.commit()
                    on_progress(task_id, "done", 1.0)
        except asyncio.CancelledError:
            with get_conn(db_path) as conn:
                cancelled = _is_cancel_requested(conn, task_id)
                if cancelled:
                    conn.execute(
                        "UPDATE video_tasks SET status='cancelled', stage='cancelled',"
                        " stage_text=?, finished_at=? WHERE id=?",
                        (CANCEL_STAGE_TEXT, _utcnow(), task_id),
                    )
                    conn.commit()
            if cancelled:
                on_progress(task_id, "cancelled", 1.0)
            else:
                raise
        except asyncio.TimeoutError:
            err_msg = f"视频渲染超时（>{int(timeout)}s），已触发熔断"
            if attempt <= retry_limit:
                with get_conn(db_path) as conn:
                    conn.execute(
                        "UPDATE video_tasks SET status='queued', progress=0.0, stage='retrying',"
                        " stage_text=?, error=?, started_at=NULL WHERE id=?",
                        (f"渲染超时，正在第 {attempt} 次自动重试", err_msg, task_id),
                    )
                    conn.commit()
                _push_pending(task_id)
                on_progress(task_id, "retrying", 0.0)
            else:
                with get_conn(db_path) as conn:
                    conn.execute(
                        "UPDATE video_tasks SET status='failed', stage='timeout', error=?,"
                        " finished_at=? WHERE id=?",
                        (err_msg, _utcnow(), task_id),
                    )
                    conn.commit()
                on_progress(task_id, "failed", 1.0)
        except Exception as e:
            err_msg = str(e)
            if attempt <= retry_limit:
                with get_conn(db_path) as conn:
                    conn.execute(
                        "UPDATE video_tasks SET status='queued', progress=0.0, stage='retrying',"
                        " stage_text=?, error=?, started_at=NULL WHERE id=?",
                        (f"渲染失败，正在第 {attempt} 次自动重试", err_msg, task_id),
                    )
                    conn.commit()
                _push_pending(task_id)
                on_progress(task_id, "retrying", 0.0)
            else:
                with get_conn(db_path) as conn:
                    conn.execute(
                        "UPDATE video_tasks SET status='failed', error=?,"
                        " finished_at=? WHERE id=?",
                        (err_msg, _utcnow(), task_id),
                    )
                    conn.commit()
                on_progress(task_id, "failed", 1.0)
        finally:
            _active_tasks.pop(task_id, None)
    return True


async def run_dispatcher(app, on_progress) -> None:
    """后台调度：取 queued → 持锁合成 → 更新状态。永不停止 (lifespan 内运行)。"""
    while True:
        try:
            drain_pending()
            await asyncio.sleep(0.5)
            await process_one_task(app, on_progress)
        except asyncio.CancelledError:
            raise
        except Exception:
            await asyncio.sleep(1)
