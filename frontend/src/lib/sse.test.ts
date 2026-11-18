/**
 * SSE 客户端单元测试：事件名与负载严格对齐 docs/API_SPEC.md §6。
 * 覆盖：事件分块解析、按事件名分发、畸形负载容错、error 事件走 onError、流关闭走 onClose。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { askStream } from "./sse";

const OK = { "Content-Type": "text/event-stream" };
const block = (name: string, data: unknown) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`;

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => vi.unstubAllGlobals());

describe("askStream SSE 解析", () => {
  it("按序分发 qa.progress / qa.citations / qa.answer / qa.done 事件", async () => {
    const calls: string[] = [];
    fetchMock.mockResolvedValue(
      new Response(
        block("qa.progress", { stage: "retrieval", message: "正在检索知识库…", progress: 0.1 }) +
          block("qa.citations", {
            citations: [
              {
                doc_id: "doc05",
                source_file: "众赢.docx",
                heading_path: "a > b",
                para_id: "doc05#p004",
                snippet: "原文",
                score: 0.87,
              },
            ],
          }) +
          block("qa.answer", { delta: "2025 年" }) +
          block("qa.answer", { delta: "研发投入 11 亿元。" }) +
          block("qa.done", { qa_record_id: 1, video_task_id: 3 }),
        { headers: OK },
      ),
    );

    askStream("众赢科技研发投入", 10, {
      onEvent: {
        "qa.progress": (p) => {
          calls.push("qa.progress");
          expect(p.stage).toBe("retrieval");
        },
        "qa.citations": (p) => {
          calls.push("qa.citations");
          expect(p.citations[0].para_id).toBe("doc05#p004");
        },
        "qa.answer": (p) => {
          calls.push("qa.answer");
          expect(typeof p.delta).toBe("string");
        },
        "qa.done": (p) => {
          calls.push("qa.done");
          expect(p.video_task_id).toBe(3);
        },
        "video.queued": () => calls.push("video.queued"),
        "video.progress": () => calls.push("video.progress"),
        "video.done": () => calls.push("video.done"),
        "video.failed": () => calls.push("video.failed"),
      },
      onClose: () => calls.push("close"),
    });

    await vi.waitFor(() => expect(calls).toContain("close"));
    expect(calls).toEqual(["qa.progress", "qa.citations", "qa.answer", "qa.answer", "qa.done", "close"]);
  });

  it("分发视频队列事件 video.queued / video.progress / video.done", async () => {
    const calls: string[] = [];
    fetchMock.mockResolvedValue(
      new Response(
        block("video.queued", { task_id: 3, queue_position: 2 }) +
          block("video.progress", { task_id: 3, progress: 0.45, stage: "render" }) +
          block("video.done", { task_id: 3, video_url: "/api/videos/3/file" }),
        { headers: OK },
      ),
    );

    askStream("q", 10, {
      onEvent: {
        "qa.progress": () => {},
        "qa.citations": () => {},
        "qa.answer": () => {},
        "qa.done": () => {},
        "video.queued": (p) => {
          calls.push("video.queued");
          expect(p.queue_position).toBe(2);
        },
        "video.progress": (p) => {
          calls.push("video.progress");
          expect(p.stage).toBe("render");
        },
        "video.done": (p) => {
          calls.push("video.done");
          expect(p.video_url).toBe("/api/videos/3/file");
        },
        "video.failed": () => {},
      },
    });

    await vi.waitFor(() => expect(calls.length).toBe(3));
    expect(calls).toEqual(["video.queued", "video.progress", "video.done"]);
  });

  it("error 事件走 onError 且不再分发给 onEvent", async () => {
    const errors: string[] = [];
    const events: string[] = [];
    fetchMock.mockResolvedValue(new Response(block("error", { code: "E_LLM_FAILED", message: "模型调用失败" }), { headers: OK }));

    askStream("q", 10, {
      onEvent: {
        "qa.progress": () => events.push("x"),
        "qa.citations": () => events.push("x"),
        "qa.answer": () => events.push("x"),
        "qa.done": () => events.push("x"),
        "video.queued": () => events.push("x"),
        "video.progress": () => events.push("x"),
        "video.done": () => events.push("x"),
        "video.failed": () => events.push("x"),
      },
      onError: (p) => errors.push(`${p.code}:${p.message}`),
    });

    await vi.waitFor(() => expect(errors).toEqual(["E_LLM_FAILED:模型调用失败"]));
    expect(events).toEqual([]);
  });

  it("畸形 JSON 负载直接丢弃，不打断后续事件", async () => {
    const calls: string[] = [];
    fetchMock.mockResolvedValue(
      new Response('event: qa.answer\ndata: {不是 json}\n\nevent: qa.answer\ndata: {"delta":"正常"}\n\n', { headers: OK }),
    );

    askStream("q", 10, {
      onEvent: {
        "qa.progress": () => {},
        "qa.citations": () => {},
        "qa.answer": (p) => calls.push(p.delta),
        "qa.done": () => {},
        "video.queued": () => {},
        "video.progress": () => {},
        "video.done": () => {},
        "video.failed": () => {},
      },
    });

    await vi.waitFor(() => expect(calls.length).toBe(1));
    expect(calls).toEqual(["正常"]);
  });

  it("请求失败（非 200）走 onError 并 onClose", async () => {
    const errors: string[] = [];
    const closed = vi.fn();
    fetchMock.mockResolvedValue(new Response(null, { status: 500, statusText: "Internal Server Error" }));

    askStream("q", 10, {
      onEvent: {
        "qa.progress": () => {},
        "qa.citations": () => {},
        "qa.answer": () => {},
        "qa.done": () => {},
        "video.queued": () => {},
        "video.progress": () => {},
        "video.done": () => {},
        "video.failed": () => {},
      },
      onError: (p) => errors.push(p.code),
      onClose: closed,
    });

    await vi.waitFor(() => expect(closed).toHaveBeenCalledOnce());
    expect(errors[0]).toMatch(/^E_HTTP_500/);
  });

  it("未知事件名安全忽略，不抛异常", async () => {
    const calls: string[] = [];
    fetchMock.mockResolvedValue(new Response('event: unknown.event\ndata: {"x":1}\n\n', { headers: OK }));

    askStream("q", 10, {
      onEvent: {
        "qa.progress": () => calls.push("x"),
        "qa.citations": () => calls.push("x"),
        "qa.answer": () => calls.push("x"),
        "qa.done": () => calls.push("x"),
        "video.queued": () => calls.push("x"),
        "video.progress": () => calls.push("x"),
        "video.done": () => calls.push("x"),
        "video.failed": () => calls.push("x"),
      },
    });

    await vi.waitFor(() => expect(calls.length).toBe(0));
  });

  it("无 data 行的事件块被忽略", async () => {
    const calls: string[] = [];
    fetchMock.mockResolvedValue(new Response("event: qa.answer\n\n", { headers: OK }));

    askStream("q", 10, {
      onEvent: {
        "qa.progress": () => calls.push("x"),
        "qa.citations": () => calls.push("x"),
        "qa.answer": () => calls.push("x"),
        "qa.done": () => calls.push("x"),
        "video.queued": () => calls.push("x"),
        "video.progress": () => calls.push("x"),
        "video.done": () => calls.push("x"),
        "video.failed": () => calls.push("x"),
      },
    });

    await new Promise((r) => setTimeout(r, 100));
    expect(calls).toEqual([]);
  });

  it("fetch 网络异常（非 AbortError）也走 onClose", async () => {
    const closed = vi.fn();
    const errors: string[] = [];
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    askStream("q", 10, {
      onEvent: {
        "qa.progress": () => {},
        "qa.citations": () => {},
        "qa.answer": () => {},
        "qa.done": () => {},
        "video.queued": () => {},
        "video.progress": () => {},
        "video.done": () => {},
        "video.failed": () => {},
      },
      onError: (p) => errors.push(p.code),
      onClose: closed,
    });
    await vi.waitFor(() => expect(closed).toHaveBeenCalledOnce());
    expect(errors).toEqual([]); // 网络异常静默关闭，不冒错误横幅
  });

  it("流读取中途异常走 onError（E_STREAM_FAILED）并 onClose", async () => {
    const closed = vi.fn();
    const errors: string[] = [];
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(block("qa.answer", { delta: "A" })));
        controller.error(new Error("connection reset"));
      },
    });
    fetchMock.mockResolvedValue(new Response(stream, { headers: OK }));
    askStream("q", 10, {
      onEvent: {
        "qa.progress": () => {},
        "qa.citations": () => {},
        "qa.answer": () => {},
        "qa.done": () => {},
        "video.queued": () => {},
        "video.progress": () => {},
        "video.done": () => {},
        "video.failed": () => {},
      },
      onError: (p) => errors.push(`${p.code}:${p.message}`),
      onClose: closed,
    });
    await vi.waitFor(() => expect(closed).toHaveBeenCalledOnce());
    expect(errors[0]).toBe("E_STREAM_FAILED:connection reset");
  });

  it("abort 终止流后不再分发后续事件", async () => {
    const calls: string[] = [];
    // 受控流：首块立即可读，后续块永不送达；abort 后读循环应终止
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(block("qa.answer", { delta: "A" })));
        // 故意不 close：模拟长连接挂起
      },
    });
    fetchMock.mockResolvedValue(new Response(stream, { headers: OK }));

    const closed = vi.fn();
    const session = askStream("q", 10, {
      onEvent: {
        "qa.progress": () => calls.push("p"),
        "qa.citations": () => calls.push("c"),
        "qa.answer": () => calls.push("a"),
        "qa.done": () => calls.push("d"),
        "video.queued": () => calls.push("q"),
        "video.progress": () => calls.push("vp"),
        "video.done": () => calls.push("vd"),
        "video.failed": () => calls.push("vf"),
      },
      onClose: closed,
    });
    await vi.waitFor(() => expect(calls).toContain("a"));
    session.abort();
    await vi.waitFor(() => expect(closed).toHaveBeenCalledOnce());
    expect(calls).toEqual(["a"]); // 仅首块，后续无事件
  });
});
