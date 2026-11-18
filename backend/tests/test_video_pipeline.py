"""视频管线测试：TTS 合成 → 分镜渲染 → ffmpeg 合成 → 队列单并发锁。

全链路真实执行（零 Mock）：edge-tts 配音 + PIL 画面 + ffmpeg 音画合成。
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.video import render_qa_video
from app.video_queue import get_task, running_count, video_lock


CITATIONS = [
    {
        "doc_id": "doc05",
        "doc_title": "西海市众赢科技有限公司介绍",
        "source_file": "西海市众赢科技有限公司介绍.docx",
        "heading_path": "西海市众赢科技有限公司介绍 > 五、研发体系与投入",
        "para_id": "doc05#p041",
        "snippet": "2025 年，公司研发投入 11 亿元，研发投入占营业收入比重超过 75%。",
        "score": 0.87,
    }
]


def test_render_qa_video_real(tmp_path):
    """端到端：题卡 + 答案 + 引用页 → TTS → 画面 → ffmpeg 合成 mp4。"""
    out = tmp_path / "qa.mp4"
    result = asyncio.run(
        render_qa_video(
            question="众赢科技 2025 年研发投入是多少？",
            answer="2025 年众赢科技研发投入达 11 亿元，占营业收入比重超过 75%。",
            citations=CITATIONS,
            out_path=out,
        )
    )
    assert out.exists(), "视频文件必须真实落盘"
    assert out.stat().st_size > 0
    assert result["segments"] >= 2, "至少题卡 + 答案两段"
    assert result["seconds"] > 0
    assert result["stages"] == ["script", "tts", "render", "mux"]


def test_video_lock_single_concurrency():
    """单并发锁：持锁期间第二任务必须等待（铁律 2 的单元层验证）。"""

    async def scenario():
        lock = video_lock()
        async with lock:
            assert lock.locked() is True
            try:
                await asyncio.wait_for(lock.acquire(), timeout=0.1)
                return "second_got_lock"  # 不应发生
            except asyncio.TimeoutError:
                return "second_blocked"  # 期望
        return "released"

    assert asyncio.run(scenario()) == "second_blocked"


def test_running_count_zero_by_default():
    with TestClient(app) as client:
        # 队列空时 running 为 0
        r = client.get("/api/video-tasks")
        assert r.status_code == 200
        body = r.json()
        assert body["running_count"] == 0
        assert isinstance(body["tasks"], list)


def test_enqueue_and_get_task(tmp_path):
    """入队 → queued → 可查询（不触发合成，仅验证队列 API）。"""
    from app.db import get_conn

    from app.video_queue import enqueue_video

    db_path = tmp_path / "t.db"
    from app import db as db_mod

    async def scenario():
        db_mod.init_db(db_path)
        with get_conn(db_path) as conn:
            conn.execute(
                "INSERT INTO qa_records (question, answer, citations, created_at)"
                " VALUES (?,?,?,?)",
                ("q", json.dumps({"answer": "a"}), json.dumps([]), "2026-01-01T00:00:00Z"),
            )
            qa_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
            conn.commit()
            task = await enqueue_video(conn, qa_id)
        with get_conn(db_path) as conn:
            fetched = get_task(conn, task["id"])
        return qa_id, fetched

    qa_id, fetched = asyncio.run(scenario())
    assert fetched["status"] == "queued"
    assert fetched["qa_record_id"] == qa_id
