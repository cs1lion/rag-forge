/**
 * REST 客户端单元测试（§2/§3/§4）：路径、method、错误模型与 204 处理。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { deleteDocument, getQaRecord, getVideoTask, listDocuments, listQaRecords, listVideoTasks, uploadDocument, videoFileUrl } from "./api";

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => vi.unstubAllGlobals());

describe("REST 客户端", () => {
  it("uploadDocument 以 multipart POST /api/documents 发送 file 字段", async () => {
    fetchMock.mockResolvedValue(Response.json({ document: { doc_id: "doc08" } }));
    const file = new File(["x"], "a.md", { type: "text/markdown" });
    await uploadDocument(file);
    expect(fetchMock).toHaveBeenCalledWith("/api/documents", expect.objectContaining({ method: "POST" }));
    const body = fetchMock.mock.calls[0][1].body as FormData;
    expect(body.get("file")).toBe(file);
  });

  it("listDocuments / listQaRecords / listVideoTasks 走 GET 正确路径", async () => {
    fetchMock.mockResolvedValue(Response.json({ documents: [], total: 0 }));
    await listDocuments();
    fetchMock.mockResolvedValue(Response.json({ records: [], total: 0 }));
    await listQaRecords();
    fetchMock.mockResolvedValue(Response.json({ tasks: [], running_count: 0 }));
    await listVideoTasks();
    expect(fetchMock).toHaveBeenNthCalledWith(1, "/api/documents", undefined);
    expect(fetchMock).toHaveBeenNthCalledWith(2, "/api/qa", undefined);
    expect(fetchMock).toHaveBeenNthCalledWith(3, "/api/video-tasks", undefined);
  });

  it("deleteDocument 走 DELETE 且 doc_id 经 encodeURIComponent 转义", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    await expect(deleteDocument("doc/08?")).resolves.toBeUndefined();
    expect(fetchMock).toHaveBeenCalledWith("/api/documents/doc%2F08%3F", expect.objectContaining({ method: "DELETE" }));
  });

  it("getQaRecord / getVideoTask 走详情路径", async () => {
    fetchMock.mockResolvedValue(Response.json({ record: { id: 1 } }));
    await getQaRecord(1);
    fetchMock.mockResolvedValue(Response.json({ task: { id: 3 } }));
    await getVideoTask(3);
    expect(fetchMock).toHaveBeenNthCalledWith(1, "/api/qa/1", undefined);
    expect(fetchMock).toHaveBeenNthCalledWith(2, "/api/video-tasks/3", undefined);
  });

  it("videoFileUrl 拼接 /api/videos/{id}/file", () => {
    expect(videoFileUrl(3)).toBe("/api/videos/3/file");
  });

  it("HTTP 错误体含 error 时携带 code/message/detail", async () => {
    fetchMock.mockResolvedValue(
      Response.json({ error: { code: "E_VALIDATION", message: "参数校验失败", detail: { field: "question" } } }, { status: 400 }),
    );
    await expect(listDocuments()).rejects.toMatchObject({ code: "E_VALIDATION", message: "参数校验失败", detail: { field: "question" } });
  });

  it("HTTP 错误体非 JSON 时回退 E_HTTP_<status> 与 statusText", async () => {
    fetchMock.mockResolvedValue(new Response("gateway down", { status: 502, statusText: "Bad Gateway" }));
    await expect(listDocuments()).rejects.toMatchObject({ code: "E_HTTP_502", message: "Bad Gateway" });
  });
});
