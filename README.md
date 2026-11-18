# 知识库问答与自动问答视频生成工作台

上传文档 → 基于知识库问答（带引用溯源）→ 自动生成问答视频；单并发视频队列、全局排队。

## 入口

| 文件 | 作用 |
| --- | --- |
| `CLAUDE.md` | 全局研发宪法 + 多 Agent 路由表（含盲测隔离禁区） |
| `DESIGN.md` | 编辑型工作台设计规范（设计令牌唯一事实来源） |
| `docs/ARCHITECTURE.md` | 系统架构：4 张表 / 三级容错解析 / 混合检索 / 双重防注入 / 视频队列 |
| `docs/API_SPEC.md` | REST + SSE 前后端对齐契约 |
| `docs/EVAL.md` | ★盲测黄金评估集（14 条用例；前端/后端 Agent 禁读） |
| `design/tokens.css` / `tokens.json` | 设计令牌实体文件（由 DESIGN.md 生成，三方校验一致） |
| `docs/SESSION_LOG.md` | 全流程 AI 协作 Session 记录 |

## 运行（基线验证）

```bash
# 后端
cd backend && pip install -r requirements.txt
cp ../.env.example .env   # 填 LLM_API_KEY 等
python -m uvicorn app.main:app --port 8000     # GET /health
python -m pytest -q                            # 冒烟测试

# 令牌三方一致性校验（任意目录）
python scripts/check_tokens.py
```

## 工程铁律（摘要，详见 CLAUDE.md §三）

严禁 Mock 数据 ｜ 全局单并发视频队列锁 ｜ 核心业务逻辑单测覆盖率 ≥ 85% ｜ 引用溯源强制 ｜ 防注入强制。

## 状态

Session 1 基线已锁定：`chore: initialize project specs, design tokens and EDD eval dataset`（commit 113a821）。
业务实现（解析/检索/问答/视频队列）按 `docs/ARCHITECTURE.md` 与 `docs/API_SPEC.md` 在后续会话迭代。
