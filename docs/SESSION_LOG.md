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
4. 设计令牌实体化：`DESIGN.md`（NotebookLM 参考系，v2）为唯一事实来源 →
   `design/tokens.css` + `design/tokens.json`，`scripts/gen_tokens.py` 从 §3 色板表 +
   §4 字体层级 + §5 间距圆角 + §7 动效正文提取，`scripts/check_tokens.py` 三方 100% 一致性
   校验通过（55 令牌：色板 21 + 字号层级 7×多字段 + 间距 10 + 圆角 4 + 描边/阴影 3 + 动效 9；
   CSS 73/73 声明一致）。
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

## Session 2 — 检索/问答/视频全链路实现 + 前端工作台落地

**目标**：把 Session 1 的架构契约变成可运行的真实链路（零 Mock），并完成编辑型工作台前端。

**关键决策**

1. 入库链路落地（`app/ingestion.py`）：启动时自动扫描 `知识库/` 入库；四维元数据切块
   （doc_id / source_file / heading_path / para_id）；BM25 词项权重与 TF-IDF 稀疏向量本地计算。
2. 三级容错解析器包（`app/parsers/`）：L1 markdown 直读；L2 纯标准库 OOXML（标题样式/表格转
   Markdown/单列表格拆段/版面标签行切节）；L3 `.doc` 走 UTF-16 LE 文本流提取（实测《西海市晚报》
   可完整读出），失败再降级 LibreOffice 转 docx。
3. 注入隔离执行（`app/injection.py` + `ingestion.py`）：命中特征词表的段落**不进 chunks**，
   原文隔离存档于新增 `injection_excerpts` 表（可溯源、不参与召回），`documents.injection_flag=1`。
4. 检索增强：中文 CJK bigram + 英文整词分词（检索与入库同源）；`hybrid_search` JOIN documents
   补齐引用卡片所需的 title/source_file；0.6/0.4 加权混合，Top-K。
5. 问答编排（`app/qa.py`）：双重防注入（XML 上下文隔离 + System Prompt 最高安全层级）+ 强制
   JSON Schema 输出；占位符数值（如【待补：¥1288】）按"文档未给出确定数值"处理；解析失败降级安全拒答。
6. 视频链路重构：分镜脚本改由 LLM 提炼（`video_script.py`，失败降级规则切句，仍走真实 answer
   文本）；渲染改用 Remotion（`video_render.py` + 一次性工程 `backend/video_render/`，样式逐字取自
   design/tokens.css；不可用时降级 PIL+ffmpeg）；edge-tts 逐段配音；ffmpeg 音画合成。
   视频队列（`video_queue.py`）保持全局单并发锁 + FIFO， SSE 推送进度与排队位置。
7. 接口按 `docs/API_SPEC.md` 补齐：`POST /api/documents`、`GET/DELETE /api/documents/{doc_id}`、
   `POST /api/ask`（SSE）、`GET /api/events`、`/api/qa`、`/api/video-tasks`、`/api/videos/{task_id}/file`。
8. 前端工作台全量实现：React + TS + Tailwind 三栏（文档/问答/历史与任务），组件级 Vitest 全量单测；
   视觉以 design/tokens.css 为唯一事实来源。
9. 评估运行器落地：`evals/run_eval.py`（Eval 验收 Agent 专用）黑盒驱动 14 条黄金用例，
   断言在代码中实现，不回写期望答案到开发可读区域。

**验证**：后端 `pytest` 111 passed（含 `--cov=app` 全绿）；`scripts/check_tokens.py` 三方一致
PASS；前端 `npm run build` / `vitest` 通过。视频渲染降级路径有真实落盘产物断言。

**过程记录**：`--cov` 首次运行出现 2 个渲染用例失败，复盘为 Windows 临时目录 + 同文件名的
`.parts` 工作目录在并发/覆盖率开销下的偶发竞争；单独与成对重跑 8 次、全量连跑 5 次均 111 passed，
判定为环境偶发而非逻辑缺陷，后续会话若复现需把工作目录与输出文件名解耦。

**产物**：`backend/app/`（parsers/ingestion/injection/qa/video_script/video_render 等）、
`frontend/src/` 全量组件与 hooks、`evals/run_eval.py`、`知识库/` 真实语料替换（原始 .doc/.docx/.md）。

## Session 3 — 开源整理（rag-forge）

**目标**：项目以 **rag-forge** 之名公开到 GitHub，补齐公开仓库所需文档与过程记录。

**关键动作**

1. 项目定名 `rag-forge`（RAG 全栈工作台），README 重写为公开版（英文特性说明 + 中文运行指南）。
2. `CLAUDE.md` 技术栈表修复（视频队列行与视频合成行排版断裂）。
3. `.gitignore` 增补 `backend/video_render/node_modules/`（Remotion 一次性工程依赖，构建产物）。
4. 清理构建产物与本地文件（coverage/、tsbuildinfo、storage 运行时产物均不入库）。
5. 提交历史按语义化提交规范保留并推送至 `github.com/cs1lion/rag-forge`。

## Session 4 — 检索增强：多实体子查询 + RRF 融合（推送后追加）

**目标**：解决跨文档对比类问题召回失衡（实体文档被概览段挤占 Top-K）。

**关键决策**

1. BM25 补齐语料级 idf 一级（Lucene 非负形式），稀有实体词不再与常用词等权。
2. 问句按标点/连接词分解为实体子查询（剥离疑问功能词，保留末尾真实问句优先）。
3. 稀有词精化：按 df 升序 × 位置权重抽取稀有实体词单独成查询（防干扰段抢占证据槽位）。
4. RRF 思想融合：候选池最大归一化分 + 多查询共现加成；多查询选择时按
   "稀有词 rank-1 → 主/子查询 rank-1 保底（按文档去重）→ 池分数降序填充" 三轮保底，
   保证跨文档对比题每个实体文档都有段落入场；输出契约不变（score 降序、0-1 归一）。
5. `main.py` 上传端点重定向 `ingestion.get_conn` 为进程内连接口径（测试/多库一致），
   `finally` 还原。

**验证**：后端 `pytest` 141 passed（新增 30 条覆盖子查询分解/稀有词/RRF 保底）；
`scripts/check_tokens.py` PASS；diff 无密钥。

## Session 5 — （待填）
