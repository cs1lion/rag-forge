"""FastAPI 入口。

会话 1 基线：仅 /health 与版本信息；业务接口（文档上传 / 问答 SSE / 视频队列）
按 docs/API_SPEC.md 在后续会话实现，本文件不预设任何 Mock 数据。
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Knowledge Q&A & Video Workbench", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health():
        return {"status": "ok", "version": "0.1.0"}

    return app


app = create_app()
