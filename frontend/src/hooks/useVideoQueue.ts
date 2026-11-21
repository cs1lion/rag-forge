import { useCallback, useState } from "react";

export interface VideoTaskItem {
  id: number;
  qa_record_id: number;
  status: "queued" | "running" | "done" | "failed" | "skipped" | "cancelled";
  progress: number;
  stage: string;
  stage_text?: string | null;
  video_path?: string | null;
  error?: string | null;
  attempt_count?: number;
}

/**
 * P3 领域拆分 Hook（视频队列域）：隔离高频视频进度 SSE 更新，并对接 P0 协作式取消接口。
 */
export function useVideoQueue(initialTasks: VideoTaskItem[] = []) {
  const [tasks, setTasks] = useState<VideoTaskItem[]>(initialTasks);

  const upsertProgress = useCallback(
    (taskId: number, stage: string, progress: number) => {
      setTasks((prev) =>
        prev.map((t) =>
          t.id === taskId
            ? {
                ...t,
                stage,
                progress,
                status:
                  stage === "done"
                    ? "done"
                    : stage === "failed"
                    ? "failed"
                    : stage === "cancelled"
                    ? "cancelled"
                    : stage === "retrying"
                    ? "queued"
                    : "running",
              }
            : t
        )
      );
    },
    []
  );

  const cancelTask = useCallback(async (taskId: number) => {
    const res = await fetch(`/api/video-tasks/${taskId}/cancel`, { method: "POST" });
    if (!res.ok) {
      throw new Error(`取消视频任务失败 (${res.status})`);
    }
    const updated: VideoTaskItem = await res.json();
    setTasks((prev) => prev.map((t) => (t.id === taskId ? updated : t)));
    return updated;
  }, []);

  return { tasks, setTasks, upsertProgress, cancelTask };
}
