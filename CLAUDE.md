# 全局研发宪法（Global Engineering Constitution）

> 本文件是本项目的最高工程法典。所有 Agent（含后续并行角色）与人在提交任何代码前，
> 必须已读并遵守本文件。违反铁律的代码不得合并。

## 一、项目定位

知识库问答与自动问答视频生成工作台：

- 用户上传文档（`.md` / `.docx` / `.doc`），系统解析入库；
- 用户提问，系统基于知识库回答，**必须给出引用溯源（哪个文档、哪个段落）**；
- 每个问答自动生成一段简单的问答视频；
- 页面展示回答进度与视频生成进度，可查看历史记录；
- **全局单并发视频队列**：同一时刻只允许一个视频合成任务，先进先出排队。

## 二、技术选型（锁定，不可擅自变更）

| 层 | 选型 | 说明 |
| --- | --- | --- |
| 后端 | FastAPI + Python 3.11+ | 异步框架，SSE 原生友好 |
| 数据库 | SQLite（`backend/storage/app.db`） | 单文件、零运维；表结构见 `docs/ARCHITECTURE.md` |
| 检索 | **零外部 Embedding 依赖**的本地混合检索 | BM25 + TF-IDF 稀疏向量本地实现；稠密向量可选但不强制 |
| 视频队列 | 单并发 + `asyncio.Lock()` | 全局一把锁，排队 FIFO |
| 前端 | React + TypeScript + Tailwind CSS | 编辑型工作台审美见 `DESIGN.md` / `design/tokens.css` |
| LLM | 通过 `LLM_BASE_URL` 调用（OpenAI 兼容协议） | Key 只经 `.env` 注入，禁止硬编码 |

## 三、工程铁律（Hard Rules）

1. **严禁 Mock 数据。** 任何测试、演示、截图都不得使用伪造的问答结果或伪造的视频文件
   冒充系统产出。测试数据必须走真实入库→检索→问答链路生成，或使用 `知识库/` 真实文档。
2. **全局单并发视频队列锁。** `video_tasks` 同一时刻 `running` 状态的任务数 ≤ 1；
   新任务必须进入 `queued` 排队，由调度器按 FIFO 提升。禁止绕过锁直接起第二条合成线程。
3. **核心业务逻辑单元测试覆盖率 ≥ 85%。** 覆盖对象至少包括：解析器（含注入隔离）、
   切块、混合检索、引用溯源、问答编排、视频队列调度。用 `pytest --cov` 度量，
   `backend/tests/` 为唯一测试目录。
4. **引用溯源强制。** 任何回答必须携带 `doc_id` + 原始文件名 + `heading_path` + `para_id`；
   无溯源的答案视为不合格。
5. **防注入强制。** 检索上下文与 System Prompt 的双重防御为架构级必选项（见
   `docs/ARCHITECTURE.md` §7），不得以"文档可信"为由省略。

## 四、盲测隔离（Anti-Data-Leakage）—— 最高优先级

为防止开发过程对测试集过拟合（"带着答案做题"），实施严格隔离：

- **`docs/EVAL.md` 是盲测黄金评估集**（含 14 条用例与评分要点）。
- **前端开发 Agent、后端开发 Agent 严禁读取 `docs/EVAL.md`**，也不得读取任何从
  `docs/EVAL.md` 派生的文件（含答案、期望输出、评分脚本的期望断言）。
- 前端/后端 Agent 只能依据 `docs/API_SPEC.md`、`docs/ARCHITECTURE.md`、`DESIGN.md`、
  `design/tokens.*` 与 `知识库/` 真实文档进行开发。
- **Eval 验收 Agent** 是唯一允许读取 `docs/EVAL.md` 的角色；其产出（验收报告）
  只允许写入 `evals/reports/`，且报告中不得反向泄露用例答案到开发 Agent 可读区域。
- 任何"为了通过某个用例而修改通用逻辑"的行为视为过拟合，违反即退回重做。

## 五、多 Agent 路由表（Role Routing Table）

| 角色 | 必读文档 | 可写目录 | **严禁读取** | 严禁写入 |
| --- | --- | --- | --- | --- |
| **架构 / 编排（本 Session）** | 全部 | 根、`docs/`、`design/`、`CLAUDE.md` | — | — |
| **前端开发 Agent** | `DESIGN.md`、`design/tokens.css`、`design/tokens.json`、`docs/API_SPEC.md`、`CLAUDE.md` | `frontend/` | **`docs/EVAL.md`**、`evals/`、`backend/app/`、`backend/tests/` | `backend/`、`docs/`、`design/`、`evals/` |
| **后端开发 Agent** | `docs/ARCHITECTURE.md`、`docs/API_SPEC.md`、`CLAUDE.md`、`知识库_文本版/00_索引.md` | `backend/app/`、`backend/tests/`、`scripts/` | **`docs/EVAL.md`**、`evals/`、`frontend/` | `frontend/`、`docs/`、`design/`、`evals/` |
| **Eval 验收 Agent** | `docs/EVAL.md`、`docs/API_SPEC.md`、`CLAUDE.md` | `evals/`、`evals/reports/` | —（可全读，但只写评估产物） | `backend/app/`、`frontend/`（只报告不实现） |

补充约定：

- 目录修改禁区以"严禁写入"列为准；跨区改动必须经架构角色评审。
- `知识库/`、`知识库_文本版/` 为只读语料，任何 Agent 不得改写原文。
- `.env` 为本地密钥，任何 Agent 不得提交、不得在日志中打印。

## 六、提交规范

- Commit message 语义化；本阶段基线提交为
  `chore: initialize project specs, design tokens and EDD eval dataset`。
- 每次提交前自检：`python -m pytest backend/tests`（覆盖率 ≥ 85%）、
  `python scripts/check_tokens.py`（令牌三方一致）、前端 `npm run build` 通过。
