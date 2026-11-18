# backend

FastAPI + SQLite。会话 1 基线仅含骨架（`/health`、4 张表建表、冒烟测试）；
业务实现（解析 / 检索 / 问答 / 视频队列）按 `docs/ARCHITECTURE.md` 与
`docs/API_SPEC.md` 在后续会话迭代。严禁 Mock 数据（`CLAUDE.md` §三 铁律 1）。

## 运行

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # 填入 LLM_API_KEY 等（.env 不入库）
uvicorn app.main:app --reload --port 8000
```

## 测试

```bash
pytest                                            # 冒烟
pytest --cov=app --cov-report=term-missing        # 会话 2 起加 --cov-fail-under=85
```
