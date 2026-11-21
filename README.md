# 知识库问答与自动问答视频生成工作台（rag-forge）

上传文档（`.md` / `.docx` / `.doc`）→ **SQLite FTS5 + 可选本地向量 RRF 混合检索** → LLM 问答（强制四维引用溯源 + **三层纵深防注入** + **声明级忠实度验真** + SSE 流式输出）→ 自动生成问答视频（大模型分镜 + edge-tts 配音 + Remotion/PIL 渲染 + ffmpeg 合成）。**全局单并发视频队列**：同一时刻只合成一个视频，其余 FIFO 排队，具备超时熔断、有限次重试与协作式取消，SSE 实时推送双进度。

> 工程宪法见 `CLAUDE.md`；接口契约见 `docs/API_SPEC.md`；架构见 `docs/ARCHITECTURE.md`；设计规范见 `DESIGN.md` + `design/tokens.*`；盲测评估集见 `docs/EVAL.md`（开发 Agent 禁读）。

## 一键启动

```
bash start.sh           # 前台：Ctrl-C 同时停前后端
bash start.sh --daemon  # 后台：日志 logs/backend.log / logs/frontend.log

```

脚本自动完成：环境检查（Python 3.11+ / Node / ffmpeg）→ `.env` 检查（缺省从模板复制并提示填 Key）→ 前后端依赖检查/安装 → 存储目录初始化 → 端口占用清理 → 启动并等待就绪 → 打印访问地址：

| 服务 | 地址 | 
| ----- | ----- | 
| 前端工作台 | http://localhost:5173 | 
| 后端 API / 健康检查 | http://localhost:8000 (`/health`) | 
| API 文档（FastAPI 自动） | http://localhost:8000/docs | 

`.env` 需配置真实 `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`（OpenAI 兼容协议；Key 只经 `.env` 注入，已 gitignore）。如需开启语义向量通道，可在 `.env` 中设置 `RETRIEVAL_USE_VECTOR=true`（默认采用本地 `BAAI/bge-small-zh-v1.5` 或 OpenAI 兼容 `/embeddings` 接口，关闭时零重型依赖纯 FTS5 运行）。

## 核心行为规则

* **SHA-256 内容寻址与热更新**：入库计算文件 SHA-256，同名未改动文档幂等跳过；内容修订时原地原子重建 `chunks`、`chunks_fts` 与 `injection_excerpts`，避免重复脏数据。

* **三层纵深防注入（OWASP LLM01）**：

  1. **入库清洗**：中英双语注入正则 + NFKC/零宽字符混淆归一化 + Base64 载荷解码 + 标签逃逸检测，命中句剥离存档至 `injection_excerpts` 并附加 `risk_warning`；

  2. **随机 Nonce XML 隔离**：每次问答生成随机 `<retrieved_evidence_{nonce}>` 数据边界，并转义片段内伪造闭合标签；

  3. **输出守卫与声明级验真**：拦截提示词/边界标签泄露（`E_PROMPT_LEAK_GUARD`），并对非拒答输出做数字/词元级忠实度核验（`verification`）。

* **拒答跳过视频生成**：当问答触发知识库外拒答（或文档范围为空）时，视频任务直接标记为 `skipped`（`stage_text` 记录“知识库未命中，已跳过视频生成”），不占用单并发队列。

* **视频队列高可用与恢复**：启动时自动将残留 `running` 重置为 `queued` 并按 `created_at` 升序重建内存队列；单任务受 `video_task_timeout_seconds` 超时熔断与有限次重试保护，支持 `POST /api/video-tasks/{task_id}/cancel` 协作式取消。

## 系统架构

```
frontend/  React 18 + TS + Tailwind（编辑型三栏工作台 + 证据透视）
    ├─ hooks/        领域状态解耦：useDocuments / useQaStream / useVideoQueue + useWorkbench
    └─ components/   含 EvidenceXRay（FTS5 / Vector / RRF 得分与声明忠实度透视）
    │  REST + SSE（fetch 流式解析，事件契约 docs/API_SPEC.md §6）
backend/   FastAPI + SQLite WAL（5 张业务表 + chunks_fts FTS5 倒排虚表）
    ├─ parsers/      三级容错解析：.md 直读 → .docx 纯标准库 OOXML → .doc UTF-16/LibreOffice
    ├─ ingestion     SHA-256 热更新 + 句界滑动窗口切块（Parent-Child）+ FTS5/向量双索引
    ├─ embeddings    可插拔本地/远端稠密向量编码（float32 BLOB 落盘，零强制依赖）
    ├─ injection     中英双语 + 零宽/NFKC 混淆 + Base64 + 标签逃逸入库剥离
    ├─ retrieval     O(log N) SQLite FTS5 BM25 + 可选语义向量 + RRF 融合 + 文档多样性保底
    ├─ qa / qa_stream  随机 Nonce XML 隔离 + 输出泄露守卫 + SSE Token 流式问答
    ├─ faithfulness  确定性声明级数字/词元忠实度验真与低召回改写判断
    ├─ video_queue   全局单并发 asyncio.Lock + DB 状态机 + 超时熔断/重试/协作式取消
    └─ video         LLM 分镜脚本（规则降级）→ edge-tts 配音 → Remotion/PIL 渲染 → ffmpeg 合成
evals/     l1_gate.py（零 LLM 成本 L1 确定性评测门禁，接入 GitHub Actions CI）

```

## 核心技术选型与权衡

| 模块 | 选型 | 为什么这么选 / 关键权衡 | 
| ----- | ----- | ----- | 
| **混合检索** | SQLite FTS5 倒排 + 可选本地向量 + RRF 融合 | 消除旧版全表扫描与双次 JSON 反序列化，万级段落保持低延迟；无外置向量库运维负担，按需开启语义通道补齐同义词召回 | 
| **入库与存储** | SQLite WAL + `busy_timeout` + SHA-256 + 滑动切块 | 单文件零配置支持并发读写；句界滑动窗口（`chunk_max_chars` / `chunk_overlap_chars`）避免长段爆窗，SHA-256 支持修订热更新 | 
| **纵深防注入** | 双语混淆入库剥离 + 随机 Nonce XML + 输出守卫 | 不依赖大模型自觉：即便未知话术绕过入库规则，随机 Nonce 数据边界与输出泄露守卫仍可拦截间接注入 | 
| **验真与评测** | `faithfulness.py` + `evals/l1_gate.py` + CI 门禁 | 超越仅校验 `para_id` 存在性，核验关键数值与词元支撑；每次 Push/PR 自动校验注入拦截率、Recall@5 与 MRR | 
| **视频队列** | `asyncio.Lock` + SQLite 状态机 + 超时熔断/取消 | 单进程内零 Redis/Celery 成本，同时防止 `ffmpeg`/`edge-tts` 卡死拖垮全局单并发队列 | 
| **Web-to-Video 设计同步** | `DESIGN.md` → `scripts/gen_design_tokens.py` → 3 份 tokens | 单一设计真理源同步生成 Web / Video / JSON 令牌，保证工作台与生成视频视觉一致 | 
| **视频渲染** | Remotion 4 主渲染 + PIL/ffmpeg 自动兜底 | Remotion 渲染 `1280x720@30fps` 数据卡片与引用框；无头浏览器异常时自动退化到 Pillow 矢量绘制 | 

## 测试与评估结果

### 自动化测试与 L1 CI 门禁

```
# 运行 P0–P3 核心架构回归测试
cd backend && python -m pytest -q tests/test_evolution_p0_p3.py

# 运行零 LLM 成本 L1 确定性评测门禁（注入拦截率 / Recall@5 / MRR / 忠实度守卫）
python3 evals/l1_gate.py

```

| 维度 | 结果 | 
| ----- | ----- | 
| **P0–P3 架构回归**（`test_evolution_p0_p3.py`） | **8/8 passed**（WAL/FTS5、双语混淆/Base64 防注入、Nonce 隔离、SHA-256 热更新、向量 RRF、声明验真、视频熔断/取消、SSE 流式拒答） | 
| **L1 确定性评测门禁**（`evals/l1_gate.py`） | **passed: true**（`injection_block_rate: 1.0` / `retrieval_recall_at_5: 1.0` / `retrieval_mrr: 1.0` / `faithfulness_and_leak_guard_ok: true`） | 
| **后端存量单测基线**（`pytest`） | 211 用例基线（含完整语料时核心覆盖率 93%；清理演示语料后依赖语料的 209 条用例自动 skip） | 
| **前端单测与构建**（`vitest` / `vite`） | 129 passed（99.5% statements），`tsc --noEmit` + `vite build` 0 错通过 | 
| **设计令牌校验**（`scripts/check_tokens.py`） | Web / Video / JSON 三方 100% 一致（PASS） | 

### EDD 盲测评估（真实 LLM + 真实语料）

评估数据集按盲测隔离原则独立构造（见 `docs/EVAL.md`），经 4 轮评估驱动硬化后：**27/27 全部通过（100%）**：

| 评估维度 | 用例数 | 结果 | 说明 | 
| ----- | ----- | ----- | ----- | 
| 正常问答 + 多实体检索 + 引用溯源 | 14 | **14/14 PASS** | 含对比/跨文档推理/数值细节/英文术语，引用定位到真实 chunk | 
| 拒答判定 + 视频 `skipped` | 4 | **4/4 PASS** | 知识库外问题 & 空文档范围均准确拒答并跳过视频生成 | 
| 注入攻击防御 | 3 | **3/3 PASS** | 语料内嵌注入 & 提问侧越狱全部拦截且不泄露指令 | 
| 端到端视频生成 & 队列 | 6 | **6/6 PASS** | 真 LLM 分镜 + `edge-tts` + Remotion 合成 MP4，单并发 FIFO 排队与状态流转完整 | 

协作记录见 `docs/SESSION_LOG.md`。盲测隔离铁律：评估报告不回写期望答案到开发可读区域；所有修复均为通用机制，无任何针对特定用例的硬编码。