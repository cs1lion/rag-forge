/**
 * SSE 客户端 —— 事件名与负载字段 100% 对齐 docs/API_SPEC.md §6。
 * POST /api/ask 返回 text/event-stream：event: <type>\ndata: <json>\n\n
 */
import type { SsePayloadMap } from "../types";

export interface SseSession {
  /** 主动终止流（组件卸载 / 重复提问时调用） */
  abort: () => void;
}

/**
 * 发起一次问答 SSE 流。onEvent 按事件名分发（各事件 payload 类型由 API_SPEC §6 锁定）；
 * onError 收到 `error` 事件负载；流关闭（done 或异常）后调用 onClose。
 */
export function askStream(
  question: string,
  historyLimit: number,
  handlers: {
    onEvent: {
      "qa.progress": (p: SsePayloadMap["qa.progress"]) => void;
      "qa.citations": (p: SsePayloadMap["qa.citations"]) => void;
      "qa.answer": (p: SsePayloadMap["qa.answer"]) => void;
      "qa.done": (p: SsePayloadMap["qa.done"]) => void;
      "video.queued": (p: SsePayloadMap["video.queued"]) => void;
      "video.progress": (p: SsePayloadMap["video.progress"]) => void;
      "video.done": (p: SsePayloadMap["video.done"]) => void;
      "video.failed": (p: SsePayloadMap["video.failed"]) => void;
    };
    onError?: (payload: SsePayloadMap["error"]) => void;
    onClose?: () => void;
  },
): SseSession {
  const controller = new AbortController();
  let activeReader: ReadableStreamDefaultReader<Uint8Array> | null = null;

  (async () => {
    let res: Response;
    try {
      res = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, history_limit: historyLimit }),
        signal: controller.signal,
      });
    } catch (err) {
      if ((err as Error).name !== "AbortError") handlers.onClose?.();
      return;
    }
    if (!res.ok || !res.body) {
      handlers.onError?.({ code: `E_HTTP_${res.status}`, message: res.statusText });
      handlers.onClose?.();
      return;
    }

    const reader = res.body.getReader();
    activeReader = reader;
    const decoder = new TextDecoder();
    let buffer = "";

    try {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        // SSE 以空行分隔事件块
        let idx: number;
        while ((idx = buffer.indexOf("\n\n")) !== -1) {
          const block = buffer.slice(0, idx);
          buffer = buffer.slice(idx + 2);
          dispatchBlock(block, handlers);
        }
      }
    } catch (err) {
      // abort() 触发 reader 取消（AbortError）：静默终止，不视为异常
      if ((err as Error)?.name !== "AbortError") {
        handlers.onError?.({ code: "E_STREAM_FAILED", message: (err as Error)?.message ?? "流读取失败" });
      }
    } finally {
      reader.releaseLock();
      handlers.onClose?.();
    }
  })();

  return {
    abort: () => {
      controller.abort();
      // 主动取消 reader：使挂起的 read() 立即以 AbortError 拒绝，走 finally 的 onClose
      void activeReader?.cancel().catch(() => {});
    },
  };
}

function dispatchBlock(
  block: string,
  handlers: {
    onEvent: {
      "qa.progress": (p: SsePayloadMap["qa.progress"]) => void;
      "qa.citations": (p: SsePayloadMap["qa.citations"]) => void;
      "qa.answer": (p: SsePayloadMap["qa.answer"]) => void;
      "qa.done": (p: SsePayloadMap["qa.done"]) => void;
      "video.queued": (p: SsePayloadMap["video.queued"]) => void;
      "video.progress": (p: SsePayloadMap["video.progress"]) => void;
      "video.done": (p: SsePayloadMap["video.done"]) => void;
      "video.failed": (p: SsePayloadMap["video.failed"]) => void;
    };
    onError?: (payload: SsePayloadMap["error"]) => void;
  },
): void {
  let eventName = "message";
  const dataLines: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) eventName = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (!dataLines.length) return;
  let payload: unknown;
  try {
    payload = JSON.parse(dataLines.join("\n"));
  } catch {
    return; // 畸形负载直接丢弃，不打断后续事件
  }
  if (eventName === "error") {
    handlers.onError?.(payload as SsePayloadMap["error"]);
    return;
  }
  // 事件名与负载一一对应（API_SPEC §6），按名取 handler
  (handlers.onEvent as Record<string, (p: unknown) => void>)[eventName]?.(payload);
}
