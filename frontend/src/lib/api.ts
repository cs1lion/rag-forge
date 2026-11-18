/**
 * REST 客户端 —— 路径与字段严格对齐 docs/API_SPEC.md。
 * 仅做传输层，不做业务状态管理。
 */
import type { DocumentRecord, QaRecordDetail, QaRecordSummary, VideoTask } from "../types";

const BASE = "/api";

export class ApiError extends Error {
  code: string;
  detail: unknown;
  constructor(code: string, message: string, detail?: unknown) {
    super(message);
    this.code = code;
    this.detail = detail;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) {
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      /* 非 JSON 错误体 */
    }
    const err = (body as { error?: { code?: string; message?: string; detail?: unknown } })?.error;
    throw new ApiError(err?.code ?? `E_HTTP_${res.status}`, err?.message ?? res.statusText, err?.detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/* ---------- 文档（§2） ---------- */

export async function uploadDocument(file: File): Promise<{ document: DocumentRecord }> {
  const form = new FormData();
  form.append("file", file);
  return request("/documents", { method: "POST", body: form });
}

export async function listDocuments(): Promise<{ documents: DocumentRecord[]; total: number }> {
  return request("/documents");
}

export async function deleteDocument(docId: string): Promise<void> {
  return request(`/documents/${encodeURIComponent(docId)}`, { method: "DELETE" });
}

/* ---------- 问答（§3） ---------- */

export async function listQaRecords(): Promise<{ records: QaRecordSummary[]; total: number }> {
  return request("/qa");
}

export async function getQaRecord(id: number): Promise<{ record: QaRecordDetail }> {
  return request(`/qa/${id}`);
}

/* ---------- 视频任务（§4） ---------- */

export async function listVideoTasks(): Promise<{ tasks: VideoTask[]; running_count: number }> {
  return request("/video-tasks");
}

export async function getVideoTask(id: number): Promise<{ task: VideoTask }> {
  return request(`/video-tasks/${id}`);
}

export function videoFileUrl(taskId: number): string {
  return `${BASE}/videos/${taskId}/file`;
}
