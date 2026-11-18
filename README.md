# rag-forge

> 知识库问答与自动问答视频生成工作台（RAG 全栈项目）

一个典型的 RAG（检索增强生成）全栈项目：**知识库问答 + 引用溯源 + 自动问答视频生成工作台**。

Upload documents → the system parses and indexes them → ask questions and get answers **grounded in your knowledge base, with per-paragraph citations** → every Q&A is turned into a short narrated video, rendered through a global single-concurrency FIFO queue.

Stack: FastAPI + SQLite · local hybrid retrieval (BM25 + TF-IDF, zero external embedding dependency) · dual prompt-injection defense · SSE progress streaming · React + TypeScript + Tailwind workbench · video pipeline (LLM storyboard → edge-tts narration → Remotion/PIL rendering → ffmpeg muxing).

## ✨ Features

- **Document ingestion, 3-level fault-tolerant parsing** — `.md` / `.docx` (pure-stdlib OOXML) / `.doc` (UTF-16 stream extraction, LibreOffice conversion fallback).
- **Local hybrid retrieval** — BM25 + TF-IDF sparse vectors computed in-process; no external embedding service.
- **Mandatory citation tracing** — every answer carries `doc_id` + source filename + `heading_path` + `para_id`.
- **Dual prompt-injection defense** — injection-signature paragraphs are quarantined at ingest (never enter the retrieval corpus); retrieved context is XML-isolated from instructions; LLM output is JSON-Schema-constrained with a safe-degradation fallback.
- **Q&A video generation** — LLM storyboard (rule-based fallback) → edge-tts / OpenAI TTS narration → Remotion rendering (PIL+ffmpeg fallback) → ffmpeg muxing; visual style reuses `design/tokens.css`.
- **Global single-concurrency video queue** — `asyncio.Lock` + DB state machine, `running ≤ 1`, FIFO promotion, real-time progress + queue position over SSE.
- **Editorial-style workbench UI** — React + TypeScript + Tailwind, design-token driven (`DESIGN.md` is the single source of truth).
- **Real data only** — no mocks anywhere; tests run the full ingest → retrieve → QA → video chain against the real corpus.

## 🗂 Repository layout

| Path | What |
| --- | --- |
| `backend/` | FastAPI app: parsers, ingestion, hybrid retrieval, QA orchestration, SSE, video queue, Remotion renderer |
| `frontend/` | React + TypeScript + Tailwind workbench (Vite + Vitest) |
| `知识库/` | Read-only source corpus the demo actually runs on |
| `design/` | Design tokens (`tokens.css` / `tokens.json`), generated from `DESIGN.md` |
| `docs/` | ARCHITECTURE / API_SPEC / EVAL (blind-test gold set) / SESSION_LOG (dev-process record) |
| `evals/` | Eval acceptance runner (`run_eval.py`); reports are gitignored |
| `scripts/` | Token consistency check, corpus inspection helpers |

## 🚀 Quick start

```bash
# 1. Backend
cd backend
pip install -r requirements.txt
cp ../.env.example .env   # fill LLM_API_KEY / LLM_BASE_URL (OpenAI-compatible)
python -m uvicorn app.main:app --port 8000   # GET /health; startup auto-ingests 知识库/

# 2. Frontend
cd ../frontend
npm install
npm run dev        # http://localhost:5173

# 3. Verify
cd ../backend && python -m pytest -q      # full backend suite
python scripts/check_tokens.py            # DESIGN.md / tokens.css / tokens.json 3-way check
```

## 🧪 Quality gates (project constitution, `CLAUDE.md` §三)

- No mock data anywhere — tests exercise the real chain end to end.
- Global single-concurrency video queue lock (`running ≤ 1`, FIFO).
- Unit-test coverage on core logic (parsers, chunking, retrieval, citation, QA, queue).
- Citation tracing mandatory; prompt-injection defense mandatory.
- Blind-test isolation: `docs/EVAL.md` (14-case gold set) is read only by the eval-acceptance role.

## 📖 Development process

`docs/SESSION_LOG.md` records every session's goals, key decisions and artifacts (spec-first baseline → ingestion/parsing → retrieval/QA → video pipeline → frontend workbench → blind eval). `docs/ARCHITECTURE.md` and `docs/API_SPEC.md` are the architecture and API contracts; `DESIGN.md` the design spec.

## ⚠️ Notes

- The LLM key lives only in `.env` (gitignored); it is never logged or echoed.
- The corpus `知识库/` is a demo set of Chinese education / company-intro documents; replace it with your own.
- Video rendering prefers Remotion (needs Node + Chrome headless) and automatically falls back to PIL + ffmpeg.
