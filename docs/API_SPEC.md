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
- 解析走三级容错（`.md` → `.docx` → `.doc` 转 docx），命中注入特征的段落被隔离不进检索语料，`documents.injection_flag=1`。
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

### POST /api/ask
提问。请求体：
```json
{ "question": "众赢科技 2025 年研发投入占营收比重是多少？", "history_limit": 10 }
```
响应：`text/event-stream`（SSE），事件序列见 §6。

### GET /api/qa
历史问答列表。响应 `200`：
```json
{ "records": [ { "id": 1, "question": "…", "answer_summary": "…", "video_task_id": 3, "video_status": "done", "created_at": "…" } ], "total": 1 }
```

### GET /api/qa/{id}
单条问答详情。响应 `200`：`{ "record": <qa_record> }`（含完整 answer 与 citations）。

## 4. 视频任务 API

### GET /api/video-tasks
队列全貌（含排队中）。响应 `200`：
```json
{ "tasks": [ { "id": 3, "qa_record_id": 5, "status": "queued", "progress": 0.0, "queue_position": 2, "created_at": "…" } ], "running_count": 1 }
```

### GET /api/video-tasks/{id}
单任务详情。响应 `200`：
```json
{ "task": { "id": 3, "qa_record_id": 5, "status": "running", "progress": 0.45, "stage": "render", "video_url": null, "error": null, "created_at": "…", "started_at": "…", "finished_at": null } }
```

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
      "score": 0.87
    }
  ]
}
```
- `refusal_reason` 非空表示安全拒答（知识库未覆盖 / 占位符未填），此时 `answer` 必须明确"文档未给出确定数值"，**不得自行补全**；
- `citations` 为空时 `answer` 必须为拒答；
- Schema 校验失败 → 降级为安全拒答，绝不输出语料注入文本。

## 6. SSE 事件流契约（POST /api/ask 响应流）

每条事件：`event: <type>\ndata: <json>\n\n`。按序可能出现：

| 事件 | data 字段 | 说明 |
| --- | --- | --- |
| `qa.progress` | `{stage, message, progress?}` | stage: `retrieval`/`generation` |
| `qa.citations` | `{citations: [ <citation> ]}` | 引用溯源（§5 结构） |
| `qa.answer` | `{delta}` | 回答增量文本（流式） |
| `qa.done` | `{qa_record_id, video_task_id, refusal_reason?}` | 问答完成，已创建/复用视频任务 |
| `video.queued` | `{task_id, queue_position}` | 视频进入排队（FIFO） |
| `video.progress` | `{task_id, progress, stage}` | progress 0.0–1.0；stage: `script`/`tts`/`render`/`mux` |
| `video.done` | `{task_id, video_url}` | 合成完成，video_url 可下载 |
| `video.failed` | `{task_id, error}` | 合成失败（任务转 failed） |
| `error` | `{code, message}` | 致命错误，流随后关闭 |

### 6.1 正常问答（含视频生成）示例
```
event: qa.progress
data: {"stage":"retrieval","message":"正在检索知识库…","progress":0.1}

event: qa.citations
data: {"citations":[{"doc_id":"doc05","source_file":"西海市众赢科技有限公司介绍.docx","heading_path":"西海市众赢科技有限公司介绍 > 五、研发体系与投入","para_id":"doc05#p041","snippet":"2025 年，公司研发投入 11 亿元…","score":0.87}]}

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
```
- `queued`：等待锁，`progress=0`，`queue_position` 由 SSE 通报；
- `running`：持有全局 `asyncio.Lock`，`progress` 递增；
- `done`：`video_path` 已落盘，`video_url` 可下载；
- `failed`：`error` 已记录，可重试（重试=新建任务）。
