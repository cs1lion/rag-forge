/**
 * 工作台状态中枢：文档库、历史问答、视频队列与当前问答流（SSE）。
 * 所有字段名对齐 docs/API_SPEC.md。
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  deleteDocument,
  deleteQaRecord,
  deleteVideoTask,
  getQaRecord,
  listDocuments,
  listQaRecords,
  listVideoTasks,
  uploadDocument,
} from "../lib/api";
import { askStream } from "../lib/sse";
import type { Citation, DocumentRecord, QaRecordSummary, RiskWarning, VideoTask } from "../types";

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
  /** 涉及文档的风险提示汇总（qa.citations 事件下发，§6） */
  riskWarnings: RiskWarning[];
  confidence: number | null;
  refusalReason: string | null;
  progress: QaProgressState | null;
  isAsking: boolean;
  /** 当前问答关联的视频任务（SSE 推进） */
  activeVideoTaskId: number | null;
  error: string | null;
  /** 提问被「至少选择一份文档」拦截时的提示 */
  askWarning: string | null;
  selectedHistoryId: number | null;

  /** 历史弹层开关 */
  historyOpen: boolean;
  setHistoryOpen: (open: boolean) => void;

  /** 本次问答生效的文档（勾选）；加载后默认全选 */
  selectedDocIds: string[];
  toggleDocSelection: (docId: string) => void;
  /** 全选 / 取消全选 */
  toggleAllDocs: () => void;

  refreshDocuments: () => Promise<void>;
  upload: (file: File) => Promise<void>;
  removeDocument: (docId: string) => Promise<void>;
  ask: (question: string) => void;
  selectHistory: (id: number) => Promise<void>;
  removeHistory: (id: number) => Promise<void>;
  removeVideoTask: (taskId: number) => Promise<void>;
  /** 选择某个视频任务为播放器当前视频（在线播放，非下载） */
  playVideoTask: (taskId: number) => void;
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
  /** 涉及文档的风险提示汇总（qa.citations 事件下发，§6） */
  const [riskWarnings, setRiskWarnings] = useState<RiskWarning[]>([]);
  const [confidence, setConfidence] = useState<number | null>(null);
  const [refusalReason, setRefusalReason] = useState<string | null>(null);
  const [progress, setProgress] = useState<QaProgressState | null>(null);
  const [isAsking, setIsAsking] = useState(false);
  const [activeVideoTaskId, setActiveVideoTaskId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedHistoryId, setSelectedHistoryId] = useState<number | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  /** 本次问答生效的文档勾选（首次加载默认全选；新上传文档默认勾选） */
  const [selectedDocIds, setSelectedDocIds] = useState<string[]>([]);
  /** 提问被「至少选择一份文档」拦截时的提示（MainPanel 展示） */
  const [askWarning, setAskWarning] = useState<string | null>(null);

  const abortRef = useRef<{ abort: () => void } | null>(null);
  const docsInitializedRef = useRef(false);
  const knownDocIdsRef = useRef<Set<string>>(new Set());

  const refreshDocuments = useCallback(async () => {
    try {
      const res = await listDocuments();
      setDocuments(res.documents);
      const ids = res.documents.map((d) => d.doc_id);
      setSelectedDocIds((prev) => {
        if (!docsInitializedRef.current) {
          // 进入时默认全选
          docsInitializedRef.current = true;
          knownDocIdsRef.current = new Set(ids);
          return ids;
        }
        // 已删除的文档移出勾选；已删除的 doc_id 从未知集合移除，便于重新入库后默认勾选
        for (const id of Array.from(knownDocIdsRef.current)) {
          if (!ids.includes(id)) knownDocIdsRef.current.delete(id);
        }
        const next = prev.filter((id) => ids.includes(id));
        for (const id of ids) {
          if (!knownDocIdsRef.current.has(id)) {
            knownDocIdsRef.current.add(id);
            next.push(id); // 新上传文档默认进入勾选范围
          }
        }
        return next;
      });
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
      // 合并策略：
      // ① 已存在任务接受服务端状态（问答 SSE 流在 video.queued 即结束，
      //    之后进度/完成只能靠服务端对齐——否则历史回看永远无视频）；
      // ② 唯一例外：本地已 done 而服务端尚未 done 时保留本地（防慢响应回退）。
      setVideoTasks((prev) => {
        const next = prev.map((local) => {
          const s = res.tasks.find((t) => t.id === local.id);
          if (!s) return local;
          if (local.status === "done" && s.status !== "done") return local;
          return { ...local, ...s };
        });
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
      // 文档库有文档但一篇未勾选：按需求提示用户选择文档，或改问空范围拒答
      if (documents.length > 0 && selectedDocIds.length === 0) {
        // 按钮已被禁用；这里作为示例问题、快捷键等入口的二次防护。
        setAskWarning("请至少勾选 1 份知识库文档");
        return;
      }
      // 重复提问前终止上一条流，避免双流交错
      abortRef.current?.abort();

      setIsAsking(true);
      setError(null);
      setAskWarning(null);
      setCurrentQuestion(trimmed);
      setAnswer("");
      setCitations([]);
      setConfidence(null);
      setRefusalReason(null);
      setProgress({ stage: "retrieval", message: "正在检索知识库…" });
      setSelectedHistoryId(null);

      const session = askStream(trimmed, 10, {
        // 请求体字段 selected_doc_ids（API_SPEC §3；doc_ids 为兼容旧客户端的等价字段）
        onEvent: {
          "qa.progress": (p) => setProgress({ stage: p.stage, message: p.message, progress: p.progress }),
          "qa.citations": (p) => {
            setCitations(p.citations);
            setRiskWarnings(p.risk_warnings ?? []);
          },
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
          "video.skipped": (p) => patchVideoTask(p.task_id, { status: "skipped", error: null }),
        },
        onError: (payload) => setError(`${payload.code}：${payload.message}`),
        onClose: () => {
          setIsAsking(false);
          void refreshVideoTasks();
          void refreshHistory();
        },
      }, selectedDocIds);
      abortRef.current = session;
    },
    [documents.length, patchVideoTask, refreshHistory, refreshVideoTasks, selectedDocIds],
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
      setHistoryOpen(false);
      setError(null);
      // 历史详情不含 risk_warnings 字段：回看时清空风险提示条
      setRiskWarnings([]);
      // 视频产物可能尚未进入本地任务列表（会话 4 前的历史记录），主动对齐一次
      void refreshVideoTasks();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "历史问答加载失败，请稍后重试。");
    }
  }, [refreshVideoTasks]);

  const removeHistory = useCallback(
    async (id: number) => {
      setError(null);
      try {
        await deleteQaRecord(id);
        setQaRecords((prev) => prev.filter((r) => r.id !== id));
        // 删除当前正在查看的记录时，回到空白提问态
        if (selectedHistoryId === id) {
          setSelectedHistoryId(null);
          setCurrentQuestion("");
          setAnswer("");
          setCitations([]);
          setConfidence(null);
          setRefusalReason(null);
          setActiveVideoTaskId(null);
        }
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "历史问答删除失败，请稍后重试。");
      }
    },
    [selectedHistoryId],
  );

  const playVideoTask = useCallback((taskId: number) => {
    setActiveVideoTaskId(taskId);
  }, []);

  const removeVideoTask = useCallback(async (taskId: number) => {
    setError(null);
    try {
      await deleteVideoTask(taskId);
      setVideoTasks((prev) => prev.filter((t) => t.id !== taskId));
      setActiveVideoTaskId((prev) => (prev === taskId ? null : prev));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "视频任务删除失败，请稍后重试。");
    }
  }, []);

  const upload = useCallback(async (file: File) => {
    setError(null);
    try {
      const res = await uploadDocument(file);
      const newDocId = res.document.doc_id;
      knownDocIdsRef.current.add(newDocId);
      // 先刷新列表，让 refresh 的「新文档默认勾选」逻辑生效；
      // 再补一次确保上传响应与列表时序差异下新文档仍在勾选集合中。
      await refreshDocuments();
      setSelectedDocIds((prev) => (prev.includes(newDocId) ? prev : [...prev, newDocId]));
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

  const toggleDocSelection = useCallback((docId: string) => {
    setAskWarning(null);
    setSelectedDocIds((prev) =>
      prev.includes(docId) ? prev.filter((id) => id !== docId) : [...prev, docId],
    );
  }, []);

  const toggleAllDocs = useCallback(() => {
    setAskWarning(null);
    setSelectedDocIds((prev) =>
      prev.length === documents.length ? [] : documents.map((d) => d.doc_id),
    );
  }, [documents]);

  // 挂载时拉取三份列表；卸载时终止未完成的 SSE 流
  useEffect(() => {
    void refreshDocuments();
    void refreshHistory();
    void refreshVideoTasks();
    return () => abortRef.current?.abort();
  }, [refreshDocuments, refreshHistory, refreshVideoTasks]);

  // 存在排队/生成中的任务时轮询对齐（问答 SSE 流在 video.queued 即结束，
  // 视频完成事件不经该流下发；轮询保证队列进度与成片及时更新到界面）。
  const hasActiveVideoTasks = videoTasks.some((t) => t.status === "queued" || t.status === "running");
  useEffect(() => {
    if (!hasActiveVideoTasks) return;
    const timer = window.setInterval(() => void refreshVideoTasks(), 3000);
    return () => window.clearInterval(timer);
  }, [hasActiveVideoTasks, refreshVideoTasks]);

  return {
    documents,
    qaRecords,
    videoTasks,
    runningCount,
    currentQuestion,
    answer,
    citations,
    riskWarnings,
    confidence,
    refusalReason,
    progress,
    isAsking,
    activeVideoTaskId,
    error,
    askWarning,
    selectedHistoryId,
    historyOpen,
    setHistoryOpen,
    selectedDocIds,
    toggleDocSelection,
    toggleAllDocs,
    refreshDocuments,
    upload,
    removeDocument,
    ask,
    selectHistory,
    removeHistory,
    removeVideoTask,
    playVideoTask,
    clearError: () => setError(null),
  };
}
