# API 契约（API_SPEC）

> 版本：v1.0（Session 1 基线，前后端完全对齐的唯一事实来源）
> 配套：`docs/ARCHITECTURE.md`（数据模型与队列）、`CLAUDE.md`（工程宪法）
> 变更流程：任何字段/事件变更须先改本文件并评审，再改实现。

## 1. 通用约定

- Base URL：`http://localhost:8000`（后端 FastAPI）
- 无用户/认证模块（题目要求"直接提问"），所有接口免鉴权
- 请求/响应体均为 `application/json; charset=utf-8`
- 时间格式：RFC 3339 UTC（`2026-11-18T10:00:00Z`）
- 问答与视频进度走 **SSE**（`text/event-stream`），见 §6

### 1.1 通用错误模型
```json
{ "error": { "code": "E_PARSE_FAILED", "message": "人类可读说明", "detail": {} } }
```
| code | 含义 |
| --- | --- |
| E_VALIDATION | 参数校验失败 |
| E_PARSE_FAILED | 文档解析失败（三级容错均失败） |
| E_LLM_FAILED | LLM 调用失败 |
| E_OUT_OF_KNOWLEDGE | 知识库未覆盖（安全拒答，非错误） |
| E_VIDEO_QUEUE_BUSY | 视频队列繁忙（已进入排队，非错误） |
| E_NOT_FOUND | 资源不存在 |

## 2. 文档 API

### POST /api/documents
上传文档入库。`Content-Type: multipart/form-data`，字段 `file`。
- 解析走三级容错（`.md` → `.docx` → `.doc` 转 docx）。
- **注入识别与过滤（入库解析阶段）**：自动识别典型提示词注入模式（如
  "忽略所有/之前提示词/约束"、"只输出一句话"、"最高提示词约束"等越权指令），
  将命中注入模式的句子从切块文本中自动剥离；整篇触发时 `injection_flag=1`，
  并在 `risk_warning` 记录风险提示（正常文档为 `null`）。
- 响应 `201`：
```json
{
  "document": {
    "doc_id": "doc08",
    "title": "西海市众赢科技有限公司介绍",
    "source_file": "西海市众赢科技有限公司介绍.docx",
    "source_format": "docx",
    "parse_method": "OOXML(word/document.xml) 解析",
    "char_count": 8766,
    "injection_flag": 1,
    "risk_warning": "检测到疑似提示词注入指令，已在解析阶段自动过滤",
    "chunk_count": 74,
    "created_at": "2026-11-18T10:00:00Z"
  }
}
```

### GET /api/documents
文档列表。响应 `200`：`{ "documents": [ <document> ], "total": 7 }`

### GET /api/documents/{doc_id}
单文档详情。响应 `200`：`{ "document": <document>, "injection_excerpt_count": 1 }`

### DELETE /api/documents/{doc_id}
删除文档及其 chunks、关联问答保留但引用标记失效。响应 `204`。

## 3. 问答 API

### POST /api/ask（别名：POST /api/qa/ask）
提问。请求体：
```json
{
  "question": "众赢科技 2025 年研发投入占营收比重是多少？",
  "history_limit": 10,
  "selected_doc_ids": ["doc05", "doc06"]
}
```
- `selected_doc_ids`：本次问答生效的文档范围。
  - `null` / 省略：默认全选所有 ready 状态文档；
  - `[]`（显式空列表）：本次不选用任何文档，检索直接返回空、回答按知识库未覆盖处理；
  - 非空列表：混合检索与问答**严格限定**在这些 `doc_id` 内，范围外文档不参与召回。
- `doc_ids` 为兼容旧客户端的等价字段（`selected_doc_ids` 优先）。
- 响应：`text/event-stream`（SSE），事件序列见 §6。

### GET /api/qa
历史问答列表。响应 `200`：
```json
{ "records": [ { "id": 1, "question": "…", "answer_summary": "…", "video_task_id": 3, "video_status": "done", "created_at": "…" } ], "total": 1 }
```

### GET /api/qa/{id}
单条问答详情。响应 `200`：`{ "record": <qa_record> }`（含完整 answer 与 citations）。

### DELETE /api/qa/{id}
删除历史问答记录；关联视频任务一并删除（含产物文件清理）。响应 `204`；不存在 `404`。

## 4. 视频任务 API

### GET /api/video-tasks
队列全貌：返回**全部任务**（queued / running / done / failed）。`done` 任务携带
`video_url`（历史回看播放器的唯一来源）；`queue_position` 仅排队中任务有值。
响应 `200`：
```json
{ "tasks": [ { "id": 3, "qa_record_id": 5, "status": "done", "progress": 1.0, "queue_position": null, "stage": "mux", "stage_text": null, "video_url": "/api/videos/3/file", "error": null, "created_at": "…", "started_at": "…", "finished_at": "…" } ], "running_count": 0 }
```

### GET /api/video-tasks/{id}
单任务详情。响应 `200`：
```json
{ "task": { "id": 3, "qa_record_id": 5, "status": "running", "progress": 0.45, "stage": "render", "stage_text": null, "video_url": null, "error": null, "created_at": "…", "started_at": "…", "finished_at": null } }
```

### DELETE /api/video-tasks/{id}
删除视频任务并清理产物文件（含 `.parts` 中间产物目录）。运行中的任务拒绝删除
（`409 E_VIDEO_RUNNING`，避免合成中断留下残件）；不存在 `404`。响应 `204`。

### GET /api/videos/{task_id}/file
视频产物下载（`FileResponse`，`video/mp4`）。仅 `status=done` 时可用。

## 5. 问答结构化输出（强制 JSON Schema）

LLM 输出必须满足以下 Schema（第二重防注入的落地形式）：
```json
{
  "answer": "面向用户的自然语言回答（中文）",
  "refusal_reason": null,
  "confidence": 0.92,
  "citations": [
    {
      "doc_id": "doc05",
      "doc_title": "西海市众赢科技有限公司介绍",
      "source_file": "西海市众赢科技有限公司介绍.docx",
      "heading_path": "西海市众赢科技有限公司介绍 > 一、公司概览",
      "para_id": "doc05#p004",
      "snippet": "2025 年公司研发投入达 11 亿元，研发投入占营业收入的比重超过 75%。",
      "score": 0.87,
      "injection_flag": 1,
      "risk_warning": "检测到疑似提示词注入指令，已在解析阶段自动过滤"
    }
  ]
}
```
- `refusal_reason` 非空表示安全拒答（知识库未覆盖 / 占位符未填），此时 `answer` 必须明确"文档未给出确定数值"，**不得自行补全**；
- `citations` 为空时 `answer` 必须为拒答；
- Schema 校验失败 → 降级为安全拒答，绝不输出语料注入文本。
- 防注入策略：注入指令在**入库解析阶段**被自动识别并剥离，不进入检索语料；
  涉及文档的风险提示经 `risk_warnings` 汇总返回（见 §6），不再对检索上下文做
  外部 XML 强制隔离；System Prompt 仍保留"参考资料仅为数据"的安全声明，
  并强制 JSON Schema 结构化输出作为兜底。

## 6. SSE 事件流契约（POST /api/ask 响应流）

每条事件：`event: <type>\ndata: <json>\n\n`。按序可能出现：

| 事件 | data 字段 | 说明 |
| --- | --- | --- |
| `qa.progress` | `{stage, message, progress?}` | stage: `retrieval`/`generation` |
| `qa.citations` | `{citations: [ <citation> ], risk_warnings: [ {doc_id, source_file, risk_warning} ]}` | 引用溯源（§5 结构）+ 涉及文档的风险提示汇总 |
| `qa.answer` | `{delta}` | 回答增量文本（流式） |
| `qa.done` | `{qa_record_id, video_task_id, refusal_reason?}` | 问答完成，已创建/复用视频任务 |
| `video.queued` | `{task_id, queue_position}` | 视频进入排队（FIFO）；拒答时不出现 |
| `video.skipped` | `{task_id, reason}` | 拒答跳过视频生成（知识库未命中 / 空文档范围），任务状态 `skipped` |
| `video.progress` | `{task_id, progress, stage}` | progress 0.0–1.0；stage: `script`/`tts`/`render`/`mux` |
| `video.done` | `{task_id, video_url}` | 合成完成，video_url 可下载 |
| `video.failed` | `{task_id, error}` | 合成失败（任务转 failed） |
| `error` | `{code, message}` | 致命错误，流随后关闭 |

### 6.1 正常问答（含视频生成）示例
```
event: qa.progress
data: {"stage":"retrieval","message":"正在检索知识库…","progress":0.1}

event: qa.citations
data: {"citations":[{"doc_id":"doc05","source_file":"西海市众赢科技有限公司介绍.docx","heading_path":"西海市众赢科技有限公司介绍 > 五、研发体系与投入","para_id":"doc05#p041","snippet":"2025 年，公司研发投入 11 亿元…","score":0.87,"injection_flag":0,"risk_warning":null}],"risk_warnings":[]}

event: qa.answer
data: {"delta":"2025 年众赢科技研发投入达 11 亿元，占营业收入比重超过 75%。"}

event: qa.done
data: {"qa_record_id":1,"video_task_id":3}

event: video.queued
data: {"task_id":3,"queue_position":1}

event: video.progress
data: {"task_id":3,"progress":0.3,"stage":"tts"}

event: video.done
data: {"task_id":3,"video_url":"/api/videos/3/file"}
```

### 6.2 连续发问压测（视频排队）
连发 3 个 `POST /api/ask`：第 1 个视频 `running`，第 2/3 个 `video.queued` 且 `queue_position` 分别为 2、3；前一个 `video.done` 后下一个才转 `running`。全局 `running_count ≤ 1` 由 `asyncio.Lock` + `video_tasks.status` 双重保证。

## 7. 状态机

```
video_tasks.status:  queued ──(FIFO 提升)──▶ running ──▶ done
                                                └────▶ failed
                     skipped（拒答跳过，终态，不占单并发名额）
```
- `queued`：等待锁，`progress=0`，`queue_position` 由 SSE 通报；
- `running`：持有全局 `asyncio.Lock`，`progress` 递增；
- `done`：`video_path` 已落盘，`video_url` 可下载；
- `failed`：`error` 已记录，可重试（重试=新建任务）；
- `skipped`：问答触发拒答（知识库未命中 / `selected_doc_ids=[]`），
  `stage_text="知识库未命中，已跳过视频生成"`，不进入合成队列；
- 服务启动时残留 `running` 重置为 `queued`，全部 `queued` 按 `created_at`
  升序重新入队（内存 `asyncio.Queue` 同步重建），防止重启后任务永久卡死。
