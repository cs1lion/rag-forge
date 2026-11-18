# AI 协作 Session 记录（全流程）

> 本文件记录各会话的目标、关键决策与产物索引，是交付物"全流程 AI 协作 Session 记录"的载体。
> 每个会话结束时由当次执行者追加一条记录；保持事实性，不写流水账。

## Session 1 — 顶层设计、工程初始化与盲测集锁定（基线）

**目标**：在写任何业务代码前完成架构契约定义与环境基线搭建。

**关键决策**

1. 技术栈锁定：FastAPI + SQLite + 零外部 Embedding 依赖的本地混合检索（BM25 + TF-IDF）
   + 单并发视频队列（`asyncio.Lock`）+ React/TypeScript/Tailwind。
2. 工程铁律入宪：严禁 Mock 数据；全局单并发视频队列锁；核心业务逻辑单测覆盖率 ≥ 85%。
3. 盲测隔离：`docs/EVAL.md` 为黄金评估集，前端/后端开发 Agent 严禁读取；Eval 验收 Agent 专用。
4. 设计令牌实体化：`DESIGN.md` 为唯一事实来源 → `design/tokens.css` + `design/tokens.json`，
   `scripts/check_tokens.py` 三方 100% 一致性校验通过（65 令牌，92/92 CSS 声明一致）。
5. 盲测黄金集：`docs/EVAL.md` 14 条用例（A 单文档事实×3 / B 易混对比×2 / C 跨文档人物并购时间线×3 /
   D 文档内干扰抗性×2 / E 域外边界拒答×2 / F 视频排队压测×2），全部锚定 `知识库/` 真实文档。
6. 三级容错解析经实测验证：`.md` 直读；`.docx` 纯标准库 OOXML（4 篇全解析成功）；
   `.doc` 为 OLE 复合文档，须先转 docx（《西海市晚报》.doc 实测 UTF-16/GBK 直解乱码）。
7. 注入隔离有实证：4 篇 docx 正文首段均为越权指令文本，解析器须隔离不进检索语料。

**产物**：`CLAUDE.md`、`DESIGN.md`、`docs/ARCHITECTURE.md`、`docs/API_SPEC.md`、
`docs/EVAL.md`、`design/tokens.css`、`design/tokens.json`、
`backend/`（骨架，`/health` 实测通过、冒烟测试 2 passed）、
`frontend/`（脚手架骨架）、`evals/`、`scripts/`（gen_tokens / check_tokens / inspect_source_docs）、
`.env.example`、`.gitignore`。

**基线提交**：`chore: initialize project specs, design tokens and EDD eval dataset`

## Session 2 — （待填）

## Session 3 — （待填）
