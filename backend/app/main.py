"""FastAPI 入口。

会话 1 基线：/health + 版本信息；启动时自动扫描知识库入库。
会话 2 接入：问答 SSE（POST /api/ask）+ 视频队列（GET /api/video-tasks 等）。
"""
import asyncio
import json
import shutil
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from .config import settings
from .db import get_conn, init_db
from .ingestion import ingest_file, load_initial_corpus
from .sse import event_stream, on_video_progress
from .video_queue import enqueue_video, get_task, queued_tasks, running_count, run_dispatcher

# 知识库语料目录（项目根 / 知识库；只读语料，任何 Agent 不得改写原文）
KB_DIR = Path(__file__).resolve().parents[2] / "知识库"

# 上传文件落盘目录（uploads 在 storage 下；解析后原始文件留存可溯源）
UPLOADS_DIR = Path(__file__).resolve().parent.parent / "storage" / "uploads"


def _document_row(row) -> dict:
    """documents 行 → API §2 响应字段（doc_id/title/source_file/...）。"""
    return {
        "doc_id": row["doc_id"],
        "title": row["title"],
        "source_file": row["source_file"],
        "source_format": row["source_format"],
        "parse_method": row["parse_method"],
        "char_count": row["char_count"],
        "injection_flag": row["injection_flag"],
        "chunk_count": row["chunk_count"],
        "created_at": row["created_at"],
    }


def _qa_summary(row) -> dict:
    """qa_records 行 → API §3 列表行（answer_summary = 回答文本前 80 字，非 JSON 原文）。"""
    answer_text = ""
    try:
        answer_obj = json.loads(row["answer"] or "{}")
        if isinstance(answer_obj, dict):
            answer_text = str(answer_obj.get("answer", "") or "")
    except (ValueError, TypeError):
        answer_text = row["answer"] or ""
    return {
        "id": row["id"],
        "question": row["question"],
        "answer_summary": answer_text[:80],
        "video_task_id": row["video_task_id"],
        "video_status": row["video_status"],
        "created_at": row["created_at"],
    }


def _qa_detail(row) -> dict:
    """qa_records 行 → API §3 详情（完整 answer + citations 数组）。"""
    base = _qa_summary(row)
    try:
        answer_obj = json.loads(row["answer"] or "{}")
    except (ValueError, TypeError):
        answer_obj = {}
    try:
        citations = json.loads(row["citations"] or "[]")
    except (ValueError, TypeError):
        citations = []
    refusal = answer_obj.get("refusal_reason") if isinstance(answer_obj, dict) else None
    if refusal == "":
        refusal = None  # 空串等价于"无拒答原因"，与 API_SPEC §5 refusal_reason 语义一致
    return {
        **base,
        "answer": answer_obj.get("answer", "") if isinstance(answer_obj, dict) else "",
        "refusal_reason": refusal,
        "confidence": answer_obj.get("confidence") if isinstance(answer_obj, dict) else None,
        "citations": citations,
    }


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    app.state.video_dir = Path(settings.storage_videos_dir)
    app.state.video_dir.mkdir(parents=True, exist_ok=True)
    # Step 1：知识库为空则自动扫描加载初始文档（零 Mock，真实入库）
    try:
        loaded = load_initial_corpus(KB_DIR)
        for r in loaded:
            print(f"[ingest] {r.doc_id} {r.source_file} chunks={r.chunk_count} "
                  f"injection={r.injection_flag}")
    except Exception as e:  # 语料缺失不阻塞启动（如纯接口测试场景）
        print(f"[ingest] initial corpus load skipped: {e}")
    # 视频队列调度器（全局单并发锁在 video_queue.video_lock）
    app.state.video_dispatcher = asyncio.create_task(run_dispatcher(app, on_video_progress))
    yield
    app.state.video_dispatcher.cancel()


def create_app() -> FastAPI:
    app = FastAPI(title="Knowledge Q&A & Video Workbench", version="0.2.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health():
        return {"status": "ok", "version": "0.2.0"}

    # ------------------------------------------------------------- 文档（§2）

    @app.post("/api/documents", status_code=201)
    async def upload_document(file: UploadFile):
        """上传文档入库（三级容错解析 + 注入隔离）。"""
        UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        ext = Path(file.filename or "").suffix.lower()
        if ext not in (".md", ".txt", ".docx", ".doc"):
            raise HTTPException(
                status_code=422,
                detail={"code": "E_VALIDATION", "message": f"不支持的格式: {ext or '(无扩展名)'}"},
            )
        dest = UPLOADS_DIR / f"{uuid.uuid4().hex}{ext}"
        with open(dest, "wb") as f:
            shutil.copyfileobj(file.file, f)
        # ingest_file 内部用默认库连接：测试/多库场景须与端点同一连接口径，
        # 临时重定向 ingestion.get_conn 到本进程的 get_conn（可被测试 monkeypatch）。
        import app.ingestion as _ing
        _orig_conn = _ing.get_conn
        _ing.get_conn = get_conn
        try:
            result = ingest_file(
                dest,
                title=Path(file.filename or "untitled").stem,
                source_file=file.filename or dest.name,
            )
        except Exception as e:
            dest.unlink(missing_ok=True)
            raise HTTPException(
                status_code=422,
                detail={"code": "E_PARSE_FAILED", "message": str(e), "detail": {}},
            ) from e
        finally:
            _ing.get_conn = _orig_conn
        return {"document": {
            "doc_id": result.doc_id,
            "title": result.title,
            "source_file": result.source_file,
            "source_format": result.source_format,
            "parse_method": result.parse_method,
            "char_count": result.char_count,
            "injection_flag": result.injection_flag,
            "chunk_count": result.chunk_count,
            "created_at": result.created_at,
        }}

    @app.get("/api/documents")
    def list_documents():
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT d.*, (SELECT COUNT(*) FROM chunks c WHERE c.doc_id = d.doc_id) AS chunk_count"
                " FROM documents d ORDER BY d.id"
            ).fetchall()
        return {"documents": [_document_row(r) for r in rows], "total": len(rows)}

    @app.get("/api/documents/{doc_id}")
    def document_detail(doc_id: str):
        with get_conn() as conn:
            row = conn.execute(
                "SELECT d.*, (SELECT COUNT(*) FROM chunks c WHERE c.doc_id = d.doc_id) AS chunk_count"
                " FROM documents d WHERE d.doc_id = ?",
                (doc_id,),
            ).fetchone()
            inj_n = conn.execute(
                "SELECT COUNT(*) AS n FROM injection_excerpts WHERE doc_id = ?", (doc_id,)
            ).fetchone()["n"]
        if row is None:
            raise HTTPException(status_code=404, detail={"code": "E_NOT_FOUND", "message": "文档不存在"})
        return {"document": _document_row(row), "injection_excerpt_count": inj_n}

    @app.delete("/api/documents/{doc_id}", status_code=204)
    def delete_document(doc_id: str):
        with get_conn() as conn:
            row = conn.execute("SELECT id FROM documents WHERE doc_id = ?", (doc_id,)).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail={"code": "E_NOT_FOUND", "message": "文档不存在"})
            conn.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))
            conn.commit()
        return Response(status_code=204)

    # ------------------------------------------------------------- 问答（SSE）

    class AskReq(BaseModel):
        question: str
        history_limit: int = 10

    @app.post("/api/ask")
    async def ask(req: AskReq):
        """问答 + 自动创建视频任务，全过程 SSE 推送（API_SPEC §6）。"""
        from .retrieval import hybrid_search
        from .tts import synth  # noqa: F401  预检 TTS 可用性（缺 Key 早失败）

        async def gen():
            # 1) 检索（本地混合，零外部 Embedding）
            yield "event: qa.progress\ndata: " + json.dumps(
                {"stage": "retrieval", "message": "正在检索知识库…", "progress": 0.1},
                ensure_ascii=False,
            ) + "\n\n"
            hits = hybrid_search(req.question, top_k=settings.retrieval_top_k)
            citations = [
                {
                    "doc_id": h["doc_id"],
                    "doc_title": h["doc_title"],
                    "source_file": h["source_file"],
                    "heading_path": h["heading_path"],
                    "para_id": h["para_id"],
                    "snippet": h["text"][:160],
                    "score": h["score"],
                }
                for h in hits
            ]
            yield "event: qa.citations\ndata: " + json.dumps(
                {"citations": citations}, ensure_ascii=False
            ) + "\n\n"

            # 2) 生成回答（真实 LLM；失败降级为安全拒答，绝不 Mock）
            yield "event: qa.progress\ndata: " + json.dumps(
                {"stage": "generation", "message": "正在生成回答…", "progress": 0.4},
                ensure_ascii=False,
            ) + "\n\n"
            from .qa import generate_answer

            try:
                answer = await generate_answer(req.question, citations)
            except Exception as e:
                answer = {
                    "answer": "知识库未覆盖该问题，或 LLM 调用失败。",
                    "refusal_reason": f"E_LLM_FAILED: {e}",
                    "confidence": 0.0,
                    "citations": [],
                }

            # 3) 流式输出回答（逐句 delta）
            text = answer.get("answer", "")
            for i in range(0, len(text), 24):
                yield "event: qa.answer\ndata: " + json.dumps(
                    {"delta": text[i : i + 24]}, ensure_ascii=False
                ) + "\n\n"
                await asyncio.sleep(0.02)

            # 4) 落库 + 创建视频任务（排队）
            with get_conn() as conn:
                cur = conn.execute(
                    "INSERT INTO qa_records (question, answer, citations, created_at)"
                    " VALUES (?,?,?,?)",
                    (req.question, json.dumps(answer, ensure_ascii=False),
                     json.dumps(citations, ensure_ascii=False), _utcnow()),
                )
                qa_id = cur.lastrowid
                conn.commit()
                task = await enqueue_video(conn, qa_id)
                conn.execute(
                    "UPDATE qa_records SET video_task_id = ? WHERE id = ?",
                    (task["id"], qa_id),
                )
                conn.commit()
            refusal = answer.get("refusal_reason") or None  # 空串 → null（§5 语义）
            yield "event: qa.done\ndata: " + json.dumps(
                {"qa_record_id": qa_id, "video_task_id": task["id"],
                 "refusal_reason": refusal},
                ensure_ascii=False,
            ) + "\n\n"
            # 真实 FIFO 排队位置（含 running 在内的未完成任务排序）
            with get_conn() as conn:
                rows = conn.execute(
                    "SELECT id FROM video_tasks WHERE status IN ('queued','running')"
                    " ORDER BY created_at, id"
                ).fetchall()
            pos = next((i + 1 for i, r in enumerate(rows) if r["id"] == task["id"]), None)
            yield "event: video.queued\ndata: " + json.dumps(
                {"task_id": task["id"], "queue_position": pos}, ensure_ascii=False
            ) + "\n\n"

        return event_stream_gen(gen())

    # ------------------------------------------------------------- SSE 通道

    @app.get("/api/events")
    async def events(request):
        return await event_stream(request)

    # ------------------------------------------------------------- 历史问答（§3）

    @app.get("/api/qa")
    def list_qa():
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT q.id, q.question, q.answer, q.citations, q.video_task_id, q.created_at,"
                " (SELECT v.status FROM video_tasks v WHERE v.id = q.video_task_id) AS video_status"
                " FROM qa_records q ORDER BY q.id"
            ).fetchall()
        return {"records": [_qa_summary(r) for r in rows], "total": len(rows)}

    @app.get("/api/qa/{qa_id}")
    def qa_detail(qa_id: int):
        with get_conn() as conn:
            row = conn.execute(
                "SELECT q.id, q.question, q.answer, q.citations, q.video_task_id, q.created_at,"
                " (SELECT v.status FROM video_tasks v WHERE v.id = q.video_task_id) AS video_status"
                " FROM qa_records q WHERE q.id = ?",
                (qa_id,),
            ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail={"code": "E_NOT_FOUND", "message": "问答记录不存在"})
        return {"record": _qa_detail(row)}

    # ------------------------------------------------------------- 视频任务

    @app.get("/api/video-tasks")
    def list_tasks():
        with get_conn() as conn:
            tasks = [
                {**t, "queue_position": i + 1}
                for i, t in enumerate(queued_tasks(conn))
            ]
            running = running_count(conn)
        return {"tasks": tasks, "running_count": running}

    @app.get("/api/video-tasks/{task_id}")
    def task_detail(task_id: int):
        with get_conn() as conn:
            t = get_task(conn, task_id)
        if t is None:
            return {"error": {"code": "E_NOT_FOUND", "message": "任务不存在"}}
        return {"task": t}

    @app.get("/api/videos/{task_id}/file")
    def video_file(task_id: int):
        with get_conn() as conn:
            t = get_task(conn, task_id)
        if t is None or t["status"] != "done" or not t["video_path"]:
            return {"error": {"code": "E_NOT_FOUND", "message": "视频未就绪"}}
        return FileResponse(t["video_path"], media_type="video/mp4")

    return app


def event_stream_gen(agen):
    """把异步生成器包成 StreamingResponse（SSE）。"""
    from fastapi.responses import StreamingResponse

    async def wrapped():
        async for chunk in agen:
            yield chunk

    return StreamingResponse(
        wrapped(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


app = create_app()
