# 知识库问答与自动问答视频生成工作台

上传文档（`.md` / `.docx` / `.doc`）→ 本地混合检索 → LLM 问答（强制引用溯源 + 双重防注入）→
自动生成问答视频（大模型分镜 + edge-tts 配音 + Remotion/PIL 渲染 + ffmpeg 合成）。
**全局单并发视频队列**：同一时刻只合成一个视频，其余 FIFO 排队，SSE 实时推送双进度。

> 工程宪法见 `CLAUDE.md`；接口契约见 `docs/API_SPEC.md`；架构见 `docs/ARCHITECTURE.md`；
> 设计规范见 `DESIGN.md` + `design/tokens.*`；盲测评估集见 `docs/EVAL.md`（开发 Agent 禁读）。

## 一键启动

```bash
bash start.sh            # 前台：Ctrl-C 同时停前后端
bash start.sh --daemon   # 后台：日志 logs/backend.log / logs/frontend.log
```

脚本自动完成：环境检查（Python 3.11+ / Node / ffmpeg）→ `.env` 检查（缺省从模板复制并提示填 Key）→
前后端依赖检查/安装 → 存储目录初始化 → 端口占用清理 → 启动并等待就绪 → 打印访问地址：

| 服务 | 地址 |
| --- | --- |
| 前端工作台 | http://localhost:5173 |
| 后端 API / 健康检查 | http://localhost:8000 （`/health`） |
| API 文档（FastAPI 自动） | http://localhost:8000/docs |

首次启动后端自动扫描 `知识库/` 真实语料入库（7 篇文档，含 4 篇带注入段落的 docx，入库即隔离）。
`.env` 需配置真实 `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`（OpenAI 兼容协议；Key 只经 `.env` 注入，已 gitignore）。

## 系统架构

```
frontend/  React 18 + TS + Tailwind（编辑型工作台三栏：问答/引用溯源/历史与队列）
   │  REST + SSE（fetch 流式解析，事件契约 docs/API_SPEC.md §6）
backend/   FastAPI + SQLite（4 张表：documents/chunks/qa_records/video_tasks）
   ├─ parsers/      三级容错解析：.md 直读 → .docx 纯标准库 OOXML → .doc UTF-16 流提取/LibreOffice 兜底
   ├─ ingestion     注入隔离（命中特征词的段落不进检索语料，隔离存档可溯源）+ 四维切块 + 稀疏向量
   ├─ retrieval     本地混合检索：BM25(语料级 idf) + TF-IDF，多实体子查询分解 + 稀有词证据保底轮转
   ├─ qa            双重防注入（XML 隔离 + System Prompt 最高安全层级）+ 强制 JSON Schema + 429 退避重试
   ├─ video_queue   全局单并发 asyncio.Lock + DB 状态机双保险，FIFO 调度
   └─ video         LLM 分镜脚本（规则降级）→ edge-tts 逐段配音 → Remotion 渲染（PIL+ffmpeg 兜底）→ 音画合成
```

## 核心技术选型与权衡

| 决策 | 选型 | 权衡 |
| --- | --- | --- |
| 检索 | **零外部 Embedding**：本地 BM25 + TF-IDF（CJK bigram 分词） | 无网络依赖、可复现、零成本；用查询级增强弥补语义召回：多实体问句分解为子查询、稀有词（人名/职位/ASCII 术语）单独精化查询、按文档去重的保底轮转——保证跨文档对比题每个实体的证据段都进 Top-K |
| 防注入 | **XML 结构隔离 + System Prompt 最高安全层级** 双防御 | 检索上下文包在 `<retrieved_documents>` 内声明"仅为数据"；模型输出强制 JSON Schema，解析失败降级安全拒答，绝不复读语料指令。入库时另有第一道闸：命中特征词的段落物理隔离不进 chunks |
| 视频队列 | **单并发 `asyncio.Lock` + `video_tasks.status` 双保险** | 锁内完成整个合成（script→tts→render→mux），DB `running` 计数恒 ≤1；FIFO 按 `created_at` 提升；SSE 通报 queue_position。压测（连发 5 问 + 0.3s 间隔并发轮询）验证不变量 |
| Web-to-Video 设计同步 | **`DESIGN.md` → `design/tokens.css`/`tokens.json` 单一事实源** | `scripts/gen_tokens.py` 生成、`check_tokens.py` 三方 100% 一致性校验（55 令牌）；前端 `src/tokens.css` 与视频渲染（Remotion 组件样式值 / PIL 兜底色板字号）逐字取自同一令牌文件——网页与视频产物视觉同源 |
| 视频渲染 | Remotion 优先，**PIL + ffmpeg 兜底** | Remotion 需要 Node/Chrome 环境；兜底路径同样复用 tokens 色板，image2 帧序列 1/4 fps 输入 → 24fps 输出（每段 4s），Windows/Linux 通用 |
| LLM 健壮性 | 429/超时**指数退避重试**（2s/4s/8s ×3） | 并发压测下网关瞬时限流不再把可用回答降级成拒答；重试耗尽才走安全拒答（零 Mock） |
| 数据库 | SQLite 单文件 | 零运维；`injection_excerpts` 隔离表与 4 张主表并存，引用溯源到 `doc_id + source_file + heading_path + para_id` 段落级 |

## 测试与评估结果

### 单元测试（全量通过）

| 端 | 命令 | 结果 | 覆盖率 |
| --- | --- | --- | --- |
| 后端 | `cd backend && pytest --cov=app tests/` | **141 passed** | **91%**（门禁 ≥85% ✅） |
| 前端 | `cd frontend && npm test` | **100 passed**（16 文件） | **99.9%** statements |
| 前端构建 | `npm run build` | ✅ tsc + vite 通过 | — |
| 设计令牌 | `python scripts/check_tokens.py` | ✅ 三方 100% 一致 | — |

后端覆盖对象：三级解析（含 .doc UTF-16 提取与注入隔离）、切块与稀疏向量、混合检索与查询增强、
引用溯源四件套、问答编排（Schema 降级/429 重试/空拒答归一）、SSE 事件契约（含 video_url/error 负载）、
TTS 双供应商、视频四阶段编排、单并发队列调度（并发 3 任务 running≤1 + FIFO）。

### EDD 盲测评估（docs/EVAL.md 14 条黄金用例）

```bash
python evals/run_eval.py --reset     # 真实后端黑盒驱动，报告 evals/eval_report.md
```

评估维度：事实正确性 / 溯源完整性 / 抗注入性 / 拒答正确性 / 队列正确性。
逐题结果、引用召回率、抗注入率、并发校验明细见 **`evals/eval_report.md`**（由运行器自动生成）。

评估驱动修复的关键缺陷（Bad Case → 通用修复，未改评估集）：
1. 检索结果缺 `doc_title`/`source_file` → SSE 流 KeyError 中断 → JOIN documents 补齐溯源四件套；
2. `/api/qa`、`/api/documents` CRUD 缺失 → 按 API_SPEC §2/§3 补齐（前端历史/上传依赖）；
3. `enqueue_video` 协程未 await → ask 流崩溃 → 修复调用；
4. BM25 查询端漏乘语料级 idf → 稀有实体词与常用词等权、跨文档召回失衡 → 教科书 BM25 分解补齐；
5. 多实体/注入长文本问题证据段被概览段挤出 Top-K → 子查询分解 + 稀有词精化 + 文档去重保底轮转；
6. LLM 网关 429 直接降级拒答 → 指数退避重试；
7. PIL 兜底渲染 ffmpeg concat 列表在 Windows 失败 + 产物未落盘 out_path + 帧时长错误 → image2 序列 1/4fps 方案；
8. SSE `video.done` 缺 `video_url`、`video.failed` error 误报 stage、broadcast 协程未调度（事件全部静默丢失）→ 修复；
9. `qa_records.video_task_id` 未回填、`answer_summary` 输出 JSON 原文、空串 refusal_reason → 契约对齐。

## 多 Agent 分工协作

按 `CLAUDE.md` §五 路由表物理隔离，防止对盲测集过拟合：

| 角色 | 职责 | 关键产物 |
| --- | --- | --- |
| 架构/编排 Session | 契约先行：宪法、API_SPEC、ARCHITECTURE、设计令牌、盲测集锁定 | `CLAUDE.md`、`docs/*`、`design/tokens.*` |
| 前端开发 Agent | 只读 DESIGN/API_SPEC 开发工作台（禁读 EVAL.md） | `frontend/`（三栏工作台 + SSE 客户端 + 100 单测） |
| 后端开发 Agent | 只读 ARCHITECTURE/API_SPEC 开发链路（禁读 EVAL.md） | `backend/app/`（解析/检索/问答/队列/视频） |
| **Eval 验收 Agent（本阶段）** | 唯一可读 EVAL.md；黑盒评估驱动迭代，修复通用缺陷 | `evals/run_eval.py`、`evals/eval_report.md`、缺陷修复、`start.sh`、本 README |

协作记录见 `docs/SESSION_LOG.md`。盲测隔离铁律：评估报告不回写期望答案到开发可读区域；
所有修复均为通用机制（检索/契约/健壮性），无任何针对特定用例的硬编码。

## 目录速览

```
├── start.sh                 # 一键冷启动（依赖检查/安装 → 初始化 → 双服务 → 打印地址）
├── CLAUDE.md / DESIGN.md    # 工程宪法 / 设计规范（唯一事实源）
├── docs/                    # API_SPEC / ARCHITECTURE / EVAL（盲测）/ SESSION_LOG
├── design/                  # tokens.css + tokens.json（55 令牌，三方校验一致）
├── 知识库/                  # 只读真实语料（7 篇：md×2 / docx×4 / doc×1）
├── backend/                 # FastAPI 应用 + tests/（141 单测，91% 覆盖）+ storage/
├── frontend/                # React 工作台（100 单测，99.9% 覆盖）
├── evals/                   # EDD 运行器 + 评估报告（Eval Agent 专用）
└── scripts/                 # 令牌生成/校验、源文档解析实测
```
