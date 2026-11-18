/**
 * 工作台状态中枢：文档库、历史问答、视频队列与当前问答流（SSE）。
 * 所有字段名对齐 docs/API_SPEC.md。
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  deleteDocument,
  getQaRecord,
  listDocuments,
  listQaRecords,
  listVideoTasks,
  uploadDocument,
} from "../lib/api";
import { askStream } from "../lib/sse";
import type { Citation, DocumentRecord, QaRecordSummary, VideoTask } from "../types";

export interface QaProgressState {
  stage: "retrieval" | "generation";
  message: string;
  progress?: number;
}

export interface Workbench {
  documents: DocumentRecord[];
  qaRecords: QaRecordSummary[];
  videoTasks: VideoTask[];
  runningCount: number;

  currentQuestion: string;
  answer: string;
  citations: Citation[];
  confidence: number | null;
  refusalReason: string | null;
  progress: QaProgressState | null;
  isAsking: boolean;
  /** 当前问答关联的视频任务（SSE 推进） */
  activeVideoTaskId: number | null;
  error: string | null;
  selectedHistoryId: number | null;

  refreshDocuments: () => Promise<void>;
  upload: (file: File) => Promise<void>;
  removeDocument: (docId: string) => Promise<void>;
  ask: (question: string) => void;
  selectHistory: (id: number) => Promise<void>;
  clearError: () => void;
}

export function useWorkbench(): Workbench {
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [qaRecords, setQaRecords] = useState<QaRecordSummary[]>([]);
  const [videoTasks, setVideoTasks] = useState<VideoTask[]>([]);
  const [runningCount, setRunningCount] = useState(0);

  const [currentQuestion, setCurrentQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [citations, setCitations] = useState<Citation[]>([]);
  const [confidence, setConfidence] = useState<number | null>(null);
  const [refusalReason, setRefusalReason] = useState<string | null>(null);
  const [progress, setProgress] = useState<QaProgressState | null>(null);
  const [isAsking, setIsAsking] = useState(false);
  const [activeVideoTaskId, setActiveVideoTaskId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedHistoryId, setSelectedHistoryId] = useState<number | null>(null);

  const abortRef = useRef<{ abort: () => void } | null>(null);

  const refreshDocuments = useCallback(async () => {
    try {
      const res = await listDocuments();
      setDocuments(res.documents);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "文档列表加载失败，请稍后重试。");
    }
  }, []);

  const refreshHistory = useCallback(async () => {
    try {
      const res = await listQaRecords();
      setQaRecords(res.records);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "历史问答加载失败，请稍后重试。");
    }
  }, []);

  const refreshVideoTasks = useCallback(async () => {
    try {
      const res = await listVideoTasks();
      // 合并而非替换：SSE 推送的实时状态是权威，全量刷新只填补本地缺失的任务，
      // 不回退本地已由 video.progress / video.done 推进的状态（避免轮询竞态）。
      setVideoTasks((prev) => {
        const next = [...prev];
        for (const st of res.tasks) {
          if (!next.some((t) => t.id === st.id)) next.push(st);
        }
        return next;
      });
      setRunningCount(res.running_count);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "视频任务列表加载失败，请稍后重试。");
    }
  }, []);

  /** 按事件即时更新本地视频任务（不存在的任务先占位，随后全量刷新对齐） */
  const patchVideoTask = useCallback((taskId: number, patch: Partial<VideoTask>) => {
    setVideoTasks((prev) => {
      if (!prev.some((t) => t.id === taskId)) {
        // 占位：字段以 SSE 通报为准，其余从缺省
        return [
          ...prev,
          {
            id: taskId,
            qa_record_id: 0,
            status: patch.status ?? "queued",
            progress: patch.progress ?? 0,
            queue_position: patch.queue_position,
            stage: patch.stage,
            video_url: patch.video_url ?? null,
            error: patch.error ?? null,
            created_at: "",
            started_at: null,
            finished_at: null,
          },
        ];
      }
      return prev.map((t) => (t.id === taskId ? { ...t, ...patch } : t));
    });
  }, []);

  const ask = useCallback(
    (question: string) => {
      const trimmed = question.trim();
      if (!trimmed) return;
      // 重复提问前终止上一条流，避免双流交错
      abortRef.current?.abort();

      setIsAsking(true);
      setError(null);
      setCurrentQuestion(trimmed);
      setAnswer("");
      setCitations([]);
      setConfidence(null);
      setRefusalReason(null);
      setProgress({ stage: "retrieval", message: "正在检索知识库…" });
      setSelectedHistoryId(null);

      const session = askStream(trimmed, 10, {
        onEvent: {
          "qa.progress": (p) => setProgress({ stage: p.stage, message: p.message, progress: p.progress }),
          "qa.citations": (p) => setCitations(p.citations),
          "qa.answer": (p) => setAnswer((prev) => prev + p.delta),
          "qa.done": (p) => {
            setActiveVideoTaskId(p.video_task_id);
            // 问答落库：刷新历史与队列全貌
            void refreshHistory();
            void refreshVideoTasks();
          },
          "video.queued": (p) => patchVideoTask(p.task_id, { status: "queued", queue_position: p.queue_position, progress: 0 }),
          "video.progress": (p) => patchVideoTask(p.task_id, { status: "running", progress: p.progress, stage: p.stage }),
          "video.done": (p) => patchVideoTask(p.task_id, { status: "done", progress: 1, video_url: p.video_url }),
          "video.failed": (p) => patchVideoTask(p.task_id, { status: "failed", error: p.error }),
        },
        onError: (payload) => setError(`${payload.code}：${payload.message}`),
        onClose: () => {
          setIsAsking(false);
          void refreshVideoTasks();
          void refreshHistory();
        },
      });
      abortRef.current = session;
    },
    [patchVideoTask, refreshHistory, refreshVideoTasks],
  );

  const selectHistory = useCallback(async (id: number) => {
    try {
      const res = await getQaRecord(id);
      const rec = res.record;
      setSelectedHistoryId(id);
      setCurrentQuestion(rec.question);
      setAnswer(rec.answer);
      setCitations(rec.citations);
      setConfidence(rec.confidence);
      setRefusalReason(rec.refusal_reason);
      setProgress(null);
      setIsAsking(false);
      setActiveVideoTaskId(rec.video_task_id);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "历史问答加载失败，请稍后重试。");
    }
  }, []);

  const upload = useCallback(async (file: File) => {
    setError(null);
    try {
      await uploadDocument(file);
      await refreshDocuments();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "文档入库失败，请检查文件格式后重试。");
    }
  }, [refreshDocuments]);

  const removeDocument = useCallback(
    async (docId: string) => {
      setError(null);
      try {
        await deleteDocument(docId);
        await refreshDocuments();
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "文档删除失败，请稍后重试。");
      }
    },
    [refreshDocuments],
  );

  // 挂载时拉取三份列表；卸载时终止未完成的 SSE 流
  useEffect(() => {
    void refreshDocuments();
    void refreshHistory();
    void refreshVideoTasks();
    return () => abortRef.current?.abort();
  }, [refreshDocuments, refreshHistory, refreshVideoTasks]);

  return {
    documents,
    qaRecords,
    videoTasks,
    runningCount,
    currentQuestion,
    answer,
    citations,
    confidence,
    refusalReason,
    progress,
    isAsking,
    activeVideoTaskId,
    error,
    selectedHistoryId,
    refreshDocuments,
    upload,
    removeDocument,
    ask,
    selectHistory,
    clearError: () => setError(null),
  };
}
