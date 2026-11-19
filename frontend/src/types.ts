/**
 * API 类型契约 —— 字段名 100% 对齐 docs/API_SPEC.md，禁改字段名。
 */

/** 文档入库响应（POST /api/documents，§2） */
export interface DocumentRecord {
  doc_id: string;
  title: string;
  source_file: string;
  source_format: "md" | "docx" | "doc";
  parse_method: string;
  char_count: number;
  injection_flag: 0 | 1;
  /** 入库解析阶段识别到疑似提示词注入时记录的风险提示；正常文档为 null */
  risk_warning?: string | null;
  chunk_count: number;
  created_at: string; // RFC 3339 UTC
}

/** 引用溯源（§5 强制 JSON Schema 的 citations 元素） */
export interface Citation {
  doc_id: string;
  doc_title: string;
  source_file: string;
  heading_path: string;
  para_id: string;
  snippet: string;
  score: number;
  /** 旧服务可能省略风险字段；UI 按安全、无风险提示兼容 */
  injection_flag?: 0 | 1;
  risk_warning?: string | null;
  /** 原文快照字段；旧接口 filename 与 source_file 同义 */
  filename?: string;
}

/** 涉及文档的风险提示汇总（qa.citations 事件负载，§6） */
export interface RiskWarning {
  doc_id: string;
  source_file: string;
  risk_warning: string;
}

/** 历史问答列表行（GET /api/qa，§3） */
export interface QaRecordSummary {
  id: number;
  question: string;
  answer_summary: string;
  video_task_id: number | null;
  video_status: VideoTaskStatus | null;
  created_at: string;
}

/** 单条问答详情（GET /api/qa/{id}） */
export interface QaRecordDetail extends QaRecordSummary {
  answer: string;
  refusal_reason: string | null;
  confidence: number;
  citations: Citation[];
}

/** 视频任务（GET /api/video-tasks，§4；status 状态机见 §7） */
export type VideoTaskStatus = "queued" | "running" | "done" | "failed" | "skipped";

export interface VideoTask {
  id: number;
  qa_record_id: number;
  status: VideoTaskStatus;
  progress: number; // 0.0-1.0
  queue_position?: number; // 仅 queued 时由 SSE/队列接口通报
  stage?: "script" | "tts" | "render" | "mux";
  video_url: string | null;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

/** SSE 事件负载（§6），事件名见 SseEventName */
export interface SsePayloadMap {
  "qa.progress": { stage: "retrieval" | "generation"; message: string; progress?: number };
  "qa.citations": { citations: Citation[]; risk_warnings: RiskWarning[] };
  "qa.answer": { delta: string };
  "qa.done": { qa_record_id: number; video_task_id: number; refusal_reason?: string };
  "video.queued": { task_id: number; queue_position: number };
  "video.progress": { task_id: number; progress: number; stage: "script" | "tts" | "render" | "mux" };
  "video.done": { task_id: number; video_url: string };
  "video.failed": { task_id: number; error: string };
  "video.skipped": { task_id: number; reason: string };
  error: { code: string; message: string };
}

export type SseEventName = keyof SsePayloadMap;
