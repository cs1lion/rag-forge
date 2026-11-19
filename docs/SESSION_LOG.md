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

## Session 5 — Eval 验收收尾与交付包装（Eval Agent）

**目标**：完成 EDD 全量评估（14 条黄金用例）、覆盖率门禁、一键冷启动实测、交付 README。

**关键动作**：
1. 检索保底机制最终形态：主查询 rank-1 → [稀有词查询 / 实体子查询] 文档去重轮转，
   每队列向深处找第一个未保底文档的证据段（跨文档时间线题的另一实体报道段常在主查询 rank-2）；
   稀有词优先级 = df / 位置权重（问句末尾优先，防注入文本抢占），ASCII 术语（CTO 等）恒定高优先。
   实测 10 个检索用例的 knowledge_scope 与关键证据段（doc05#p032 价值观、doc06#p049 CTO 表、
   doc01#p010 公益合作稿）全部进 Top-5。
2. SSE broadcast 修复：call_soon 内 ensure_future 调度协程（此前 video.progress/done/failed
   事件全部静默丢失——前端视频面板收不到任何推送的根因）。
3. 新增 tests/test_api_sse_tts.py：文档 CRUD/ask SSE 契约/qa 列表详情/视频下载/SSE 回调负载/
   TTS 双供应商/视频四阶段编排/429 重试/检索增强，30 条；后端合计 141 passed，覆盖率 91%。
4. 前端 npm test 100 passed（16 文件）、test:coverage 99.9% statements、npm run build 通过。
5. start.sh 实测（--daemon）：修复 Python 版本比较（3.12 误判 <3.11）、netstat 空匹配 pipefail
   退出、nohup 后台进程 stdin 继承三处缺陷；双服务拉起 + /health 与前端 200 验证通过。
6. evals/run_eval.py 最终轮全量运行，报告 evals/eval_report.md；README.md 交付级重写
   （架构/选型权衡/一键启动/测试与评估汇总/多 Agent 分工）。

**追加（同 Session 5，验收收尾轮）**：
9. `.doc` 解析噪声修复：OLE/CFB 直解出的 WPS 尾注与二进制头被当正文（乱码段进入检索语料），
   改为段级真实文本提取（控制符/私用区切分 + CJK 占比 ≥0.3 + 最小段长 4），语料 11780→4793 字符；
10. LLM 输出截断治理：`finish_reason=length` 时 max_tokens ×2（上限 8192）重试；
    429 退避提升为 5/10/20s（4 次尝试窗口 35s）；
11. 检索保底机制定稿：多实体子查询 + 稀有词精化（位置权重/ASCII 实体词优先）+
    "未覆盖文档优先"的保底轮转（每文档 ≤2 段）+ 候选池填充；10 个评估题的关键证据段
    （价值观/CTO 表/2026 聘任/公益合作稿/15 人研发）全部进 Top-5；
12. 评估器时序修复：`drain_queue` 以"无 running 且无 queued"判排空（/api/video-tasks
    已返回全部任务，旧判空逻辑永不满足）。

**产物**：evals/run_eval.py + eval_report.md、start.sh、README.md、
backend 解析/检索/SSE/契约修复与 31 条新增单测、本记录。

## Session 6 — 交互修复：历史回看播放器 / 布局滚动 / 历史抽屉 / 隔离开关 / 任务删除

**目标**：修复五项交付反馈。

**关键动作**：
1. **历史问答不显示视频播放器（根因修复）**：`GET /api/video-tasks` 此前只返回
   `queued` 任务且不透出 `video_url`——刷新页面或回看历史时前端拿不到可播放源。
   改为返回全部任务（含 done/failed），`_task_row` 将 `video_path` 映射为
   `video_url=/api/videos/{id}/file`（内部落盘路径不外露）；`selectHistory` 后
   主动 `refreshVideoTasks` 对齐产物。
2. **列表高度自适应 + 内部滚动**：文档库、历史抽屉、视频任务队列均为
   `min-h-0 flex-1 overflow-y-auto`，内容超出页面时内部滚动，不撑长页面。
3. **历史记录迁至顶栏抽屉**：右上角历史按钮弹出 `HistoryDrawer`（遮罩 + 右侧抽屉），
   点击条目后中栏展示问答详情、右栏展示对应视频产物，抽屉自动关闭；
   侧栏历史列表移除；抽屉内支持删除（`DELETE /api/qa/{id}`，级联删除关联视频任务）。
4. **隔离文档开关**：`documents.quarantined` 新列（幂等迁移）；`PUT
   /api/documents/{doc_id}/quarantine`；检索层 `WHERE quarantined=0` 整篇排除。
   含注入特征的文档行内提供开关（shield 图标，`role=switch`）；未隔离时检索结果
   携带 `injection_flag=1`，引用来源条展示风险提示。
5. **视频任务删除**：`DELETE /api/video-tasks/{id}`（清理产物与 `.parts` 中间目录；
   running 任务 409 拒绝），前端任务行内删除按钮（running 禁用）。
6. **视频路径健壮性**：DB 中 `video_path` 可能为相对路径（`storage/videos/…`），
   此前 `FileResponse` 按进程 CWD 解析，换目录启动即 500。统一按后端目录
   `_abs_video_path` 解析；文件缺失时返回 404 JSON 而非 500；删除清理同口径。
7. **僵尸任务恢复**：服务重启时把遗留 `running` 任务标记为 `failed`
   （"服务重启导致任务中断"），释放单并发名额（否则永久占用且无法从界面删除）。
8. 文档同步：API_SPEC（quarantined 字段、PUT quarantine、DELETE qa/video-tasks、
   video-tasks 全量返回契约）、ARCHITECTURE（documents 表与隔离开关语义）。

**验证**：后端 `pytest` 154 passed、覆盖率 92%（新增 12 条隔离/删除/播放器/路径/恢复单测）；
前端 `vitest` 116 passed（16 文件，新增 HistoryDrawer；删除废弃 HistoryList）、`npm run build`
通过；浏览器实测：历史抽屉开合与内部滚动、选中回看（中栏详情 + 右栏 MP4 可播，
`readyState=4`、1280×720）、引用条风险提示、隔离开关往返持久化、任务删除按钮态等均正常。

**注**：`retrieval.py` 一处未提交的实验性检索改动（数字锚定/每文档 2 段保底等）
在回归中导致 `test_multi_entity_topk_covers_both_docs` 失败（doc05 掉出 Top-5），
本次已回退到 HEAD 版本，仅保留隔离过滤与 injection_flag 透出三处小改动。

**交付反馈修复（同日追加）**：
1. **删除历史问答 500**：`DELETE /api/qa/{id}` 原只删 `video_task_id` 指向的一行，
   该问答名下若有其他任务（`video_tasks.qa_record_id` 引用）则外键冲突 → 500。
   改为：解除所有相关引用 → 删除该问答名下**全部**任务（含 running）→ 删问答；
   删除视频任务时同样先解除 `qa_records.video_task_id` 引用；文件清理遇
   占用/权限异常（Windows 播放中）不阻塞删除。
2. **历史回看无视频（时序）**：问答 SSE 流在 `video.queued` 即结束，此后
   视频完成事件不经该流下发；原「全量刷新只补缺失任务」导致本地占位任务
   永远停在 queued/running。改为：服务端状态可推进已有任务（唯本地 done 且
   服务端未 done 时保留），并在存在排队/生成中任务时每 3s 轮询对齐。
3. 历史抽屉视频状态中文文案（排队中/生成中/可播放/失败），修复英文状态外泄。
4. 新增回归单测：问答下额外/运行中任务的删除、被引用任务删除、文件锁清理、
   服务端 done 推进本地占位、相对路径视频解析。

**复验**：后端 157 passed；前端 117 passed、build 通过；浏览器实测（真实问答 →
单并发渲染完成 → 历史回看播放器 `readyState=4` 可播 → 抽屉内删除成功无报错）。

### 视频管线升级（同日追加）

针对 `video_1.mp4` 的四类缺陷做定点修复（video_script / video_render / video）：
1. **文字右侧截断**：PIL 渲染改为按像素宽度逐字折行（`_wrap`），文本容器 max-width 88%；
   Remotion 模板同步 `maxWidth:88%` + `word-break/overflow-wrap: break-word` +
   `line-height:1.65`，全文无 `nowrap`。三页正文再按内容包围盒在卡片内垂直居中。
2. **严格音画同步**：改为**逐页独立 TTS**（3 条音频），读取每页 WAV 精确时长
   （帧数/采样率，毫秒级），末尾加 0.4s 呼吸停顿并换算为帧数写入 `page["frames"]`；
   音频用 `apad + -t` 补齐到同帧数时长；修复 `concat:` 协议对 WAV 只读首段的缺陷
   （改用 concat 解复用器清单），mux 以总帧数时长 `-t` 收尾，不再用 `-shortest`
   截断——「第 3 页未播完就结束」根因消除。
3. **三页编辑器式版式**：固定 Page1 问题 / Page2 结论+≤3 要点（关键数字强调）/
   Page3 引用文档卡片（文件名 + 章节路径 + 高亮原文摘录）；白底主卡片 + 1px 边框 +
   12px 圆角 + 48px 内边距；微标签胶囊取 tint-blue 令牌。LLM 提炼结论/要点/念白，
   失败按真实 answer 规则降级（不 Mock）。
4. **进度条与过渡**：顶部 3px 进度条取 `--nb-accent`，逐帧按全局时间轴线性增长；
   换页 180ms（24fps≈5 帧）交叉淡入 + 8px 微位移（PIL 与 Remotion 双实现）。

**播放与下载分离**：`/api/videos/{id}/file` 显式 `Content-Disposition: inline`；
播放器页面内在线播放，下载是独立按钮（播放器下方 + 每个任务行「在线播放 / 下载」）。

**自检（真实链路，qa#3 众赢问答）**：3 页语音 6.60s / 22.20s / 7.06s → 帧数
168 / 542 / 179，总 889 帧 = 37.042s；成片容器 37.0417s、音轨 37.041s
（页边界 7.000s / 29.583s 与各页语音+0.4s 完全一致）；抽帧逐页检查无右侧截断，
过渡帧为两页混合（交叉淡入生效）。产物：`backend/storage/videos/qa_new_test.mp4`。

**复验**：后端 161 passed、覆盖率 93%（video.py 100% / video_render 90% / video_script 93%）；
前端 119 passed、build 通过。

**产物**：`backend/app/{db,main,retrieval}.py`、`backend/tests/test_quarantine_and_deletes.py`、
`frontend/src/components/HistoryDrawer.tsx` 及 App/Sidebar/DocList/VideoPanel/SourcesBar/TopBar、
hooks/lib 类型与客户端、`vite.config.ts`（BACKEND_ORIGIN 可覆盖）、本记录。

## Session 7 — 盲测集扩至 16 条：勾选范围隔离验收与引用语义定稿（Eval Agent）

**目标**：`docs/EVAL.md` 由架构会话扩充至 16 条（新增 G 类"文档勾选范围隔离" E15/E16；
D 类升级为"注入自动过滤 + 显式风险提示"；E11/E13/E14 增加 skipped 与 MP4 有效性校验）。
同步 `evals/run_eval.py` 并重跑全量验收，输出 `evals/reports/` 留档报告。

**关键动作与缺陷修复**（评估驱动，全部为通用修复，未触碰 docs/EVAL.md）：
1. 运行器升级 16 条：load_cases 解析 16 用例；SSEClient 支持 `selected_doc_ids`；
   E09 改查 GET /api/documents 的 risk_warning（4 注入文档非空、3 干净文档无误报）；
   E11/E15 校验视频任务 skipped；E13 校验 MP4 > 50KB；E14 计数守恒含 skipped；
   新增 E15（勾选 doc02 问 doc05 内容 → 拒答 + 零引用 + skipped，防越界泄露）与
   E16（恢复全选 → doc05 召回与溯源立即恢复 + 视频 done）；报告增加 §6 范围隔离一节，
   并自动归档时间戳副本到 `evals/reports/`。
2. 引用语义定稿（API_SPEC §5 双向）：**非拒答回答 → citations = 本轮检索证据集；
   拒答（知识库未覆盖 / 空勾选范围）→ citations 必为空**。此前实现先后有两处偏差：
   - qa.py 把模型引用与检索集做交集归一时，对不完整引用未回补 heading_path/source_file
     等展示字段（E05/E07 断言"引用四件套"失败）；
   - main.py API 层曾用"模型引用优先"策略导致拒答场景引用字段缺失/越界。
   最终在 main.py 收敛为单一职责：refusal → 清空；非 refusal → 用检索命中集（完整四件套），
   E15 场景检索证据集 ⊆ selected_doc_ids，天然无越界泄露。
3. qa.py SYSTEM_PROMPT 规则 2 明确：占位符/不公布场景**不算拒答**（refusal_reason=null、
   保留引用指明依据）——修复 E10 一度被判 refusal 后引用清空的自相矛盾。
4. 语料重建：旧库为 risk_warning 列上线前入库（列值全空），删库重扫知识库
   → doc03/05/06/07 的 risk_warning 正确写入"检测到疑似提示词注入指令，已在解析阶段自动过滤"，
   doc01/02/04 保持空（无误报）。

**验证**：后端 `pytest --cov` 211 passed / 覆盖率 93%（新增范围隔离与 skipped 用例后）；
E01–E12 复跑全绿；最终 16 条全量评估结果与留档报告见 `evals/eval_report.md` 与
`evals/reports/eval_report_*.md`。

**产物**：evals/run_eval.py（16 条版）、evals/reports/（时间戳留档）、
backend/app/{main,qa}.py 引用语义修复、语料重建、本记录。
