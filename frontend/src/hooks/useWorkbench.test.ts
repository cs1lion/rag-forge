/**
 * useWorkbench 状态中枢单元测试（Step 2/3）：
 * 覆盖历史问答切换（点击回看）与 SSE 实时更新驱动的状态流转。
 */
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useWorkbench } from "./useWorkbench";
import type { VideoTask } from "../types";

const QA_SUMMARY = {
  id: 1,
  question: "众赢科技 2025 年研发投入占营收比重是多少？",
  answer_summary: "超过 75%。",
  video_task_id: 3,
  video_status: "done" as const,
  created_at: "2026-11-18T10:00:00Z",
};

const QA_DETAIL = {
  ...QA_SUMMARY,
  answer: "2025 年众赢科技研发投入达 11 亿元，占营业收入比重超过 75%。",
  refusal_reason: null,
  confidence: 0.92,
  citations: [
    {
      doc_id: "doc05",
      doc_title: "西海市众赢科技有限公司介绍",
      source_file: "西海市众赢科技有限公司介绍.docx",
      heading_path: "西海市众赢科技有限公司介绍 > 五、研发体系与投入",
      para_id: "doc05#p041",
      snippet: "2025 年，公司研发投入 11 亿元…",
      score: 0.87,
    },
  ],
};

function sseStream(events: { name: string; data: unknown }[]) {
  const body = events.map((e) => `event: ${e.name}\ndata: ${JSON.stringify(e.data)}\n\n`).join("");
  return new Response(body, { headers: { "Content-Type": "text/event-stream" } });
}

const EVENTS = [
  { name: "qa.progress", data: { stage: "retrieval", message: "正在检索知识库…", progress: 0.1 } },
  {
    name: "qa.citations",
    data: { citations: QA_DETAIL.citations },
  },
  { name: "qa.answer", data: { delta: "2025 年众赢科技研发投入达 11 亿元，" } },
  { name: "qa.answer", data: { delta: "占营业收入比重超过 75%。" } },
  { name: "qa.done", data: { qa_record_id: 1, video_task_id: 3 } },
  { name: "video.queued", data: { task_id: 3, queue_position: 1 } },
  { name: "video.progress", data: { task_id: 3, progress: 0.5, stage: "tts" } },
  { name: "video.done", data: { task_id: 3, video_url: "/api/videos/3/file" } },
];

describe("useWorkbench 文档上传与删除", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url === "/api/documents" && init?.method === "POST")
          return Response.json({
            document: {
              doc_id: "doc09",
              title: "新文档",
              source_file: "new.md",
              source_format: "md",
              parse_method: "MD 直读",
              char_count: 10,
              injection_flag: 0,
              risk_warning: null,
              chunk_count: 1,
              created_at: "2026-11-18T10:00:00Z",
            },
          });
        if (url === "/api/documents")
          return Response.json({
            documents: [
              {
                doc_id: "doc09",
                title: "新文档",
                source_file: "new.md",
                source_format: "md",
                parse_method: "MD 直读",
                char_count: 10,
                injection_flag: 0,
                risk_warning: null,
                chunk_count: 1,
                created_at: "2026-11-18T10:00:00Z",
              },
            ],
            total: 1,
          });
        if (url === "/api/qa") return Response.json({ records: [], total: 0 });
        if (url === "/api/video-tasks") return Response.json({ tasks: [], running_count: 0 });
        return new Response(null, { status: 404 });
      }),
    );
  });

  afterEach(() => vi.unstubAllGlobals());

  it("upload 成功后刷新文档列表并默认勾选新文档", async () => {
    const { result } = renderHook(() => useWorkbench());
    await waitFor(() => expect(result.current.selectedDocIds).toEqual(["doc09"]));
    expect(result.current.documents).toHaveLength(1);
    expect(result.current.error).toBeNull();
  });

  it("已有文档取消勾选时，上传新文档仍会默认勾选", async () => {
    const initial = {
      doc_id: "doc01",
      title: "旧文档",
      source_file: "old.md",
      source_format: "md",
      parse_method: "MD 直读",
      char_count: 10,
      injection_flag: 0,
      risk_warning: null,
      chunk_count: 1,
      created_at: "2026-11-18T10:00:00Z",
    };
    let uploaded = false;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url === "/api/documents" && init?.method === "POST") {
          uploaded = true;
          return Response.json({ document: { ...initial, doc_id: "doc09", title: "新文档", source_file: "new.md" } });
        }
        if (url === "/api/documents")
          return Response.json({ documents: uploaded ? [initial, { ...initial, doc_id: "doc09", title: "新文档", source_file: "new.md" }] : [initial], total: uploaded ? 2 : 1 });
        if (url === "/api/qa") return Response.json({ records: [], total: 0 });
        if (url === "/api/video-tasks") return Response.json({ tasks: [], running_count: 0 });
        return new Response(null, { status: 404 });
      }),
    );
    const { result } = renderHook(() => useWorkbench());
    await waitFor(() => expect(result.current.selectedDocIds).toEqual(["doc01"]));
    act(() => result.current.toggleAllDocs());
    expect(result.current.selectedDocIds).toEqual([]);
    await act(() => result.current.upload(new File(["# x"], "new.md", { type: "text/markdown" })));
    expect(result.current.selectedDocIds).toEqual(["doc09"]);
  });

  it("upload 失败写入错误且不抛出", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url === "/api/documents" && init?.method === "POST")
          return Response.json({ error: { code: "E_PARSE_FAILED", message: "三级容错均失败" } }, { status: 400 });
        if (url === "/api/documents") return Response.json({ documents: [], total: 0 });
        if (url === "/api/qa") return Response.json({ records: [], total: 0 });
        if (url === "/api/video-tasks") return Response.json({ tasks: [], running_count: 0 });
        return new Response(null, { status: 404 });
      }),
    );
    const { result } = renderHook(() => useWorkbench());
    await act(() => result.current.upload(new File(["x"], "bad.docx", { type: "application/octet-stream" })));
    expect(result.current.error).toBe("三级容错均失败");
  });

  it("removeDocument 成功与失败均不抛异常，失败写 error", async () => {
    let failDelete = false;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (method === "DELETE" && url === "/api/documents/doc02" && failDelete)
        return new Response(null, { status: 500, statusText: "boom" });
      if (method === "DELETE") return new Response(null, { status: 204 });
      if (url === "/api/documents") return Response.json({ documents: [], total: 0 });
      if (url === "/api/qa") return Response.json({ records: [], total: 0 });
      if (url === "/api/video-tasks") return Response.json({ tasks: [], running_count: 0 });
      return new Response(null, { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useWorkbench());
    await act(() => result.current.removeDocument("doc01"));
    expect(fetchMock).toHaveBeenCalledWith("/api/documents/doc01", expect.objectContaining({ method: "DELETE" }));
    expect(result.current.error).toBeNull();

    failDelete = true;
    await act(() => result.current.removeDocument("doc02"));
    // 无 error 体的 HTTP 错误回退 statusText；关键是错误被捕获且不抛出
    expect(result.current.error).toBeTruthy();
  });

  it("clearError 清空错误", async () => {
    const { result } = renderHook(() => useWorkbench());
    act(() => result.current.clearError());
    expect(result.current.error).toBeNull();
  });
});

describe("useWorkbench 历史切换与 SSE 实时更新", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url === "/api/documents") return Response.json({ documents: [], total: 0 });
        if (url === "/api/qa") return Response.json({ records: [QA_SUMMARY], total: 1 });
        if (url === "/api/qa/1") return Response.json({ record: QA_DETAIL });
        if (url === "/api/video-tasks") return Response.json({ tasks: [], running_count: 0 });
        if (url === "/api/qa/ask") return sseStream(EVENTS);
        return new Response(null, { status: 404 });
      }),
    );
  });

  afterEach(() => vi.unstubAllGlobals());

  it("挂载时加载历史问答，点击历史条目回看完整问答与引用", async () => {
    const { result } = renderHook(() => useWorkbench());
    await waitFor(() => expect(result.current.qaRecords).toHaveLength(1));
    expect(result.current.qaRecords[0].question).toBe(QA_SUMMARY.question);

    await act(() => result.current.selectHistory(1));

    expect(result.current.selectedHistoryId).toBe(1);
    expect(result.current.currentQuestion).toBe(QA_SUMMARY.question);
    expect(result.current.answer).toBe(QA_DETAIL.answer);
    expect(result.current.citations).toHaveLength(1);
    expect(result.current.citations[0].para_id).toBe("doc05#p041");
    expect(result.current.citations[0].heading_path).toContain("五、研发体系与投入");
    expect(result.current.confidence).toBe(0.92);
    expect(result.current.activeVideoTaskId).toBe(3);
  });

  it("SSE 流实时推进：进度 → 引用 → 流式回答 → 视频队列四态", async () => {
    const { result } = renderHook(() => useWorkbench());
    await waitFor(() => expect(result.current.qaRecords).toHaveLength(1));

    act(() => result.current.ask("众赢科技 2025 年研发投入占营收比重是多少？"));
    expect(result.current.isAsking).toBe(true);
    expect(result.current.currentQuestion).toBe("众赢科技 2025 年研发投入占营收比重是多少？");

    await waitFor(() => expect(result.current.isAsking).toBe(false));

    // 引用已渲染
    expect(result.current.citations).toHaveLength(1);
    // 流式回答拼合完整
    expect(result.current.answer).toBe("2025 年众赢科技研发投入达 11 亿元，占营业收入比重超过 75%。");
    // 关联视频任务
    expect(result.current.activeVideoTaskId).toBe(3);
    // 视频任务经 SSE 推进到 done（qa.done 刷新后由 video.* 事件补丁）
    await waitFor(() =>
      expect(result.current.videoTasks.some((t) => t.id === 3 && t.status === "done")).toBe(true),
    );
    const task = result.current.videoTasks.find((t) => t.id === 3)!;
    expect(task.video_url).toBe("/api/videos/3/file");
  }, 15000);

  it("重复提问前终止上一条 SSE 流（abort）", async () => {
    const { result } = renderHook(() => useWorkbench());
    await waitFor(() => expect(result.current.qaRecords).toHaveLength(1));

    let askCount = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url === "/api/qa/ask") {
          askCount += 1;
          return sseStream([EVENTS[0]]);
        }
        if (url === "/api/documents") return Response.json({ documents: [], total: 0 });
        if (url === "/api/qa") return Response.json({ records: [QA_SUMMARY], total: 1 });
        if (url === "/api/qa/1") return Response.json({ record: QA_DETAIL });
        if (url === "/api/video-tasks") return Response.json({ tasks: [], running_count: 0 });
        return new Response(null, { status: 404 });
      }),
    );

    act(() => result.current.ask("问题一"));
    act(() => result.current.ask("问题二"));
    // 两次提问产生两次流会话
    expect(askCount).toBe(2);
    expect(result.current.currentQuestion).toBe("问题二");
  });

  it("空问题不发起请求", async () => {
    const { result } = renderHook(() => useWorkbench());
    await waitFor(() => expect(result.current.qaRecords).toHaveLength(1));
    act(() => result.current.ask("   "));
    expect(result.current.isAsking).toBe(false);
    expect(result.current.currentQuestion).toBe("");
  });

  it("SSE error 事件写入错误横幅并结束提问态", async () => {
    const { result } = renderHook(() => useWorkbench());
    await waitFor(() => expect(result.current.qaRecords).toHaveLength(1));
    // 仅 /api/ask 返回 error 流，列表接口保持成功，避免 onClose 的刷新覆盖错误
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url === "/api/qa/ask")
          return new Response('event: error\ndata: {"code":"E_LLM_FAILED","message":"模型调用失败"}\n\n', { headers: { "Content-Type": "text/event-stream" } });
        if (url === "/api/documents") return Response.json({ documents: [], total: 0 });
        if (url === "/api/qa") return Response.json({ records: [QA_SUMMARY], total: 1 });
        if (url === "/api/video-tasks") return Response.json({ tasks: [], running_count: 0 });
        return new Response(null, { status: 404 });
      }),
    );
    act(() => result.current.ask("触发错误"));
    await waitFor(() => expect(result.current.isAsking).toBe(false));
    expect(result.current.error).toBe("E_LLM_FAILED：模型调用失败");
  });

  it("video.failed 事件将任务置为 failed 并记录原因", async () => {
    const { result } = renderHook(() => useWorkbench());
    await waitFor(() => expect(result.current.qaRecords).toHaveLength(1));
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url === "/api/qa/ask")
          return new Response(
            'event: qa.done\ndata: {"qa_record_id":1,"video_task_id":9}\n\n' +
              'event: video.failed\ndata: {"task_id":9,"error":"TTS 服务超时"}\n\n',
            { headers: { "Content-Type": "text/event-stream" } },
          );
        if (url === "/api/documents") return Response.json({ documents: [], total: 0 });
        if (url === "/api/qa") return Response.json({ records: [QA_SUMMARY], total: 1 });
        if (url === "/api/video-tasks") return Response.json({ tasks: [], running_count: 0 });
        return new Response(null, { status: 404 });
      }),
    );
    act(() => result.current.ask("q"));
    await waitFor(() =>
      expect(result.current.videoTasks.some((t) => t.id === 9 && t.status === "failed" && t.error === "TTS 服务超时")).toBe(true),
    );
  });

  it("selectHistory 失败时写入错误且不覆盖当前内容", async () => {
    const { result } = renderHook(() => useWorkbench());
    await waitFor(() => expect(result.current.qaRecords).toHaveLength(1));
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url === "/api/qa/1") return new Response(null, { status: 500, statusText: "boom" });
        if (url === "/api/documents") return Response.json({ documents: [], total: 0 });
        if (url === "/api/qa") return Response.json({ records: [QA_SUMMARY], total: 1 });
        if (url === "/api/video-tasks") return Response.json({ tasks: [], running_count: 0 });
        return new Response(null, { status: 404 });
      }),
    );
    await act(() => result.current.selectHistory(1));
    expect(result.current.selectedHistoryId).toBeNull();
    // 错误模型无 error 体时回退 statusText（API_SPEC §1.1 之外的人类可读兜底）
    expect(result.current.error).toBeTruthy();
    expect(result.current.answer).toBe("");
  });

  it("全量刷新只填补本地缺失任务，不覆盖 SSE 已推进的状态", async () => {
    const serverTask: VideoTask = {
      id: 3,
      qa_record_id: 1,
      status: "queued",
      progress: 0,
      queue_position: 1,
      video_url: null,
      error: null,
      created_at: "2026-11-18T10:00:00Z",
      started_at: null,
      finished_at: null,
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url === "/api/qa/ask")
          return new Response(
            'event: qa.done\ndata: {"qa_record_id":1,"video_task_id":3}\n\n' +
              'event: video.done\ndata: {"task_id":3,"video_url":"/api/videos/3/file"}\n\n',
            { headers: { "Content-Type": "text/event-stream" } },
          );
        if (url === "/api/documents") return Response.json({ documents: [], total: 0 });
        if (url === "/api/qa") return Response.json({ records: [QA_SUMMARY], total: 1 });
        // 服务器返回旧的 queued 状态与一个新任务 id=8
        if (url === "/api/video-tasks")
          return Response.json({ tasks: [serverTask, { ...serverTask, id: 8, status: "queued", queue_position: 2 }], running_count: 0 });
        return new Response(null, { status: 404 });
      }),
    );
    const { result } = renderHook(() => useWorkbench());
    await waitFor(() => expect(result.current.qaRecords).toHaveLength(1));
    act(() => result.current.ask("q"));
    await waitFor(() => expect(result.current.videoTasks.some((t) => t.id === 3 && t.status === "done")).toBe(true));
    await waitFor(() => expect(result.current.videoTasks.some((t) => t.id === 8)).toBe(true));
    // SSE 权威：id=3 保持 done，不被服务器 queued 回退
    const t3 = result.current.videoTasks.find((t) => t.id === 3)!;
    expect(t3.status).toBe("done");
    expect(t3.video_url).toBe("/api/videos/3/file");
  });

  it("服务端已完成的任务会推进本地占位任务（历史回看可播放的前提）", async () => {
    // 问答流只到 video.queued；渲染完成后服务端列表返回 done + video_url，
    // 本地占位任务必须被推进为 done（否则历史回看永远无视频）。
    const doneTask: VideoTask = {
      id: 3,
      qa_record_id: 1,
      status: "done",
      progress: 1,
      stage: "mux",
      video_url: "/api/videos/3/file",
      error: null,
      created_at: "2026-11-18T10:00:00Z",
      started_at: "2026-11-18T10:00:01Z",
      finished_at: "2026-11-18T10:00:30Z",
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url === "/api/qa/ask")
          return new Response(
            'event: qa.done\ndata: {"qa_record_id":1,"video_task_id":3}\n\n' +
              'event: video.queued\ndata: {"task_id":3,"queue_position":1}\n\n',
            { headers: { "Content-Type": "text/event-stream" } },
          );
        if (url === "/api/documents") return Response.json({ documents: [], total: 0 });
        if (url === "/api/qa") return Response.json({ records: [QA_SUMMARY], total: 1 });
        if (url === "/api/video-tasks") return Response.json({ tasks: [doneTask], running_count: 0 });
        return new Response(null, { status: 404 });
      }),
    );
    const { result } = renderHook(() => useWorkbench());
    await waitFor(() => expect(result.current.qaRecords).toHaveLength(1));
    act(() => result.current.ask("q"));
    await waitFor(() => {
      const t = result.current.videoTasks.find((x) => x.id === 3);
      expect(t?.status).toBe("done");
      expect(t?.video_url).toBe("/api/videos/3/file");
    });
  });

  it("挂载时列表接口失败写入错误横幅，clearError 可清空", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(null, { status: 500, statusText: "boom" })));
    const { result } = renderHook(() => useWorkbench());
    await waitFor(() => expect(result.current.error).toBeTruthy());
    act(() => result.current.clearError());
    expect(result.current.error).toBeNull();
  });

  it("文档全部取消勾选时 ask 不发请求并给出固定提示", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url === "/api/documents") return Response.json({ documents: [{ doc_id: "doc01" }], total: 1 });
        if (url === "/api/qa") return Response.json({ records: [QA_SUMMARY], total: 1 });
        if (url === "/api/video-tasks") return Response.json({ tasks: [], running_count: 0 });
        return new Response(null, { status: 404 });
      }),
    );
    const { result } = renderHook(() => useWorkbench());
    await waitFor(() => expect(result.current.selectedDocIds).toEqual(["doc01"]));
    act(() => result.current.toggleAllDocs());
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockClear();
    act(() => result.current.ask("不应发送"));
    expect(fetchMock).not.toHaveBeenCalled();
    expect(result.current.askWarning).toBe("请至少勾选 1 份知识库文档");
    expect(result.current.isAsking).toBe(false);
    act(() => result.current.toggleDocSelection("doc01"));
    expect(result.current.askWarning).toBeNull();
  });

  it("video.skipped 事件更新为正常终态且不记录失败原因", async () => {
    const { result } = renderHook(() => useWorkbench());
    await waitFor(() => expect(result.current.qaRecords).toHaveLength(1));
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url === "/api/qa/ask")
          return sseStream([
            { name: "qa.done", data: { qa_record_id: 1, video_task_id: 3 } },
            { name: "video.skipped", data: { task_id: 3, reason: "知识库未命中" } },
          ]);
        if (url === "/api/documents") return Response.json({ documents: [], total: 0 });
        if (url === "/api/qa") return Response.json({ records: [QA_SUMMARY], total: 1 });
        if (url === "/api/video-tasks") return Response.json({ tasks: [], running_count: 0 });
        return new Response(null, { status: 404 });
      }),
    );
    act(() => result.current.ask("q"));
    await waitFor(() => expect(result.current.videoTasks[0]?.status).toBe("skipped"));
    expect(result.current.videoTasks[0]?.error).toBeNull();
    expect(result.current.activeVideoTaskId).toBe(3);
  });

  it("selectHistory 成功后关闭历史弹层（historyOpen 复位）", async () => {
    const { result } = renderHook(() => useWorkbench());
    await waitFor(() => expect(result.current.qaRecords).toHaveLength(1));
    act(() => result.current.setHistoryOpen(true));
    expect(result.current.historyOpen).toBe(true);
    await act(() => result.current.selectHistory(1));
    expect(result.current.historyOpen).toBe(false);
  });
});

describe("useWorkbench 删除", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (method === "DELETE" && url === "/api/qa/1") return new Response(null, { status: 204 });
        if (url === "/api/qa/1") return Response.json({ record: QA_DETAIL });
        if (method === "DELETE" && url === "/api/video-tasks/3") return new Response(null, { status: 204 });
        if (url === "/api/documents") return Response.json({ documents: [], total: 0 });
        if (url === "/api/qa") return Response.json({ records: [QA_SUMMARY], total: 1 });
        if (url === "/api/video-tasks") return Response.json({ tasks: [], running_count: 0 });
        return new Response(null, { status: 404 });
      }),
    );
  });

  afterEach(() => vi.unstubAllGlobals());

  it("removeHistory 删除后从列表移除并清空当前选中态", async () => {
    const { result } = renderHook(() => useWorkbench());
    await waitFor(() => expect(result.current.qaRecords).toHaveLength(1));
    await act(async () => { await result.current.selectHistory(1); });
    expect(result.current.selectedHistoryId).toBe(1);

    await act(async () => { await result.current.removeHistory(1); });
    expect(result.current.qaRecords).toHaveLength(0);
    expect(result.current.selectedHistoryId).toBeNull();
    expect(result.current.currentQuestion).toBe("");
    expect(result.current.error).toBeNull();
  });

  it("removeVideoTask 删除后从队列移除，若为当前任务则复位 activeVideoTaskId", async () => {
    const { result } = renderHook(() => useWorkbench());
    await waitFor(() => expect(result.current.qaRecords).toHaveLength(1));
    await act(async () => { await result.current.selectHistory(1); });
    expect(result.current.activeVideoTaskId).toBe(3);

    await act(async () => { await result.current.removeVideoTask(3); });
    expect(result.current.videoTasks).toHaveLength(0);
    expect(result.current.activeVideoTaskId).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it("删除原文档后历史回看仍渲染保存的引用快照", async () => {
    const { result } = renderHook(() => useWorkbench());
    await waitFor(() => expect(result.current.qaRecords).toHaveLength(1));
    await act(async () => { await result.current.removeDocument("doc05"); });
    await act(async () => { await result.current.selectHistory(1); });
    expect(result.current.error).toBeNull();
    expect(result.current.citations[0]?.source_file).toBe("西海市众赢科技有限公司介绍.docx");
    expect(result.current.citations[0]?.heading_path).toContain("五、研发体系与投入");
    expect(result.current.citations[0]?.snippet).toContain("研发投入 11 亿元");
  });
});
