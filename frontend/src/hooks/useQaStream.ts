import { useCallback, useRef, useState } from "react";

export interface ScoreBreakdown {
  fts: number;
  vector: number;
  rrf: number;
}

export interface EvidenceCitation {
  doc_id: string;
  source_file: string;
  heading_path: string;
  para_id: string;
  snippet?: string;
  text?: string;
  score: number;
  score_breakdown?: ScoreBreakdown;
}

export interface VerificationReport {
  faithfulness_score: number;
  total_claims: number;
  supported_claims: number;
  unsupported_claims: Array<{ claim: string; reason: string; overlap: number }>;
}

/**
 * P3 领域拆分 Hook（问答流域）：消费 SSE Token 级问答流，支持 AbortController 中断与证据透视。
 */
export function useQaStream(streamEndpoint = "/api/qa/stream") {
  const [answer, setAnswer] = useState("");
  const [citations, setCitations] = useState<EvidenceCitation[]>([]);
  const [verification, setVerification] = useState<VerificationReport | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const stopStream = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setStreaming(false);
  }, []);

  const askStream = useCallback(
    async (question: string, docIds: string[]) => {
      abortRef.current?.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;

      setAnswer("");
      setCitations([]);
      setVerification(null);
      setError(null);
      setStreaming(true);

      try {
        const res = await fetch(streamEndpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question, doc_ids: docIds }),
          signal: ctrl.signal,
        });
        if (!res.ok || !res.body) {
          throw new Error(`流式问答请求失败 (${res.status})`);
        }
        const reader = res.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let buffer = "";
        let currentEvent = "message";

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";

          for (const rawLine of lines) {
            const line = rawLine.trim();
            if (!line) {
              currentEvent = "message";
              continue;
            }
            if (line.startsWith("event:")) {
              currentEvent = line.slice(6).trim();
            } else if (line.startsWith("data:")) {
              const payload = JSON.parse(line.slice(5).trim());
              if (currentEvent === "retrieval") {
                setCitations(payload.citations ?? []);
              } else if (currentEvent === "token") {
                setAnswer((prev) => prev + (payload.delta ?? ""));
              } else if (currentEvent === "verified") {
                setAnswer(payload.answer ?? "");
                setCitations(payload.citations ?? []);
                setVerification(payload.verification ?? null);
              }
            }
          }
        }
      } catch (err) {
        if ((err as Error).name !== "AbortError") {
          setError((err as Error).message || "流式问答异常");
        }
      } finally {
        setStreaming(false);
      }
    },
    [streamEndpoint]
  );

  return { answer, citations, verification, streaming, error, askStream, stopStream };
}
