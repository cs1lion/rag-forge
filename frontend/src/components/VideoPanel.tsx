/**
 * 视频工作室（Step 4）：当前问答的 MP4 播放器 + 下方视频任务队列面板。
 * 队列严格按 DESIGN.md §3 成对功能色块 + 线性图标展示四种状态：
 * queued（排队位次与前方人数）、running/processing（实时进度条）、
 * done/completed（可播放）、failed（失败原因）。
 * 全局单并发：running_count ≤ 1（API_SPEC §6.2）。
 */
import { Icon } from "./Icon";
import type { VideoTask } from "../types";
import { formatPercent } from "../lib/format";

interface VideoPanelProps {
  tasks: VideoTask[];
  runningCount: number;
  activeTaskId: number | null;
}

/** 成对功能色块：底浅一档、墨深一档（DESIGN.md §3） */
const STATUS_TINT: Record<VideoTask["status"], { bg: string; ink: string; icon: "queue" | "spinner" | "play" | "alert" }> = {
  queued: { bg: "var(--nb-tint-amber-bg)", ink: "var(--nb-tint-amber-ink)", icon: "queue" },
  running: { bg: "var(--nb-tint-blue-bg)", ink: "var(--nb-tint-blue-ink)", icon: "spinner" },
  done: { bg: "var(--nb-tint-green-bg)", ink: "var(--nb-tint-green-ink)", icon: "play" },
  failed: { bg: "var(--nb-tint-amber-bg)", ink: "var(--nb-tint-amber-ink)", icon: "alert" },
};

const STAGE_LABEL: Record<NonNullable<VideoTask["stage"]>, string> = {
  script: "脚本",
  tts: "语音合成",
  render: "画面渲染",
  mux: "音画合成",
};

const STATUS_LABEL: Record<VideoTask["status"], string> = {
  queued: "排队中",
  running: "生成中",
  done: "已完成",
  failed: "失败",
};

export function VideoPanel({ tasks, runningCount, activeTaskId }: VideoPanelProps) {
  const active = tasks.find((t) => t.id === activeTaskId) ?? null;

  return (
    <div className="flex min-h-0 flex-1 flex-col" style={{ gap: "var(--space-16)" }}>
      {/* 当前问答视频播放器 */}
      <section aria-label="当前问答视频">
        {active?.status === "done" && active.video_url ? (
          <video
            controls
            src={active.video_url}
            preload="metadata"
            style={{ width: "100%", height: "auto", borderRadius: "var(--nb-radius-md)", border: "var(--border-width) solid var(--nb-border)" }}
          >
            您的浏览器不支持视频播放，请下载后观看。
          </video>
        ) : (
          <div
            className="flex flex-col items-center justify-center"
            style={{
              aspectRatio: "16 / 9",
              border: "var(--border-width) solid var(--nb-border)",
              borderRadius: "var(--nb-radius-md)",
              backgroundColor: "var(--nb-bg-subtle)",
              gap: "var(--space-8)",
              padding: "var(--space-16)",
              textAlign: "center",
            }}
          >
            <Icon name="film" size={24} style={{ color: "var(--nb-text-tertiary)" }} />

            <p style={{ margin: 0, fontSize: "var(--text-body-size)", color: "var(--nb-text-tertiary)" }}>
              {active?.status === "running"
                ? "视频正在合成，完成后即可在此播放。"
                : active?.status === "queued"
                  ? "视频正在排队，前方任务合成完成后开始生成。"
                  : active?.status === "failed"
                    ? "本次视频合成失败，可重新提问生成新任务。"
                    : "提问后系统将自动生成问答视频。"}
            </p>
          </div>
        )}
      </section>

      {/* 队列全貌 */}
      <div
        className="flex items-center justify-between"
        style={{ fontSize: "var(--text-meta-size)", color: "var(--nb-text-tertiary)" }}
      >
        <span>任务队列 · 单并发</span>
        <span>
          运行中 {runningCount} / 1 · 共 {tasks.length} 条
        </span>
      </div>

      <ul
        role="list"
        aria-label="视频任务队列"
        style={{ margin: 0, padding: 0, listStyle: "none", borderTop: "var(--border-width) solid var(--nb-border)" }}
      >
        {tasks.length === 0 ? (
          <li style={{ fontSize: "var(--text-body-size)", color: "var(--nb-text-tertiary)", padding: "var(--space-12) 0" }}>
            暂无视频任务，提出第一个问题后自动创建。
          </li>
        ) : (
          tasks.map((task) => (
            <VideoTaskRow key={task.id} task={task} isActive={task.id === activeTaskId} />
          ))
        )}
      </ul>
    </div>
  );
}

/** 生成物条目样式（DESIGN.md §6）：色块图标 + 标题 + 一行说明，条目间 1px 分隔线，不加外框 */
function VideoTaskRow({ task, isActive }: { task: VideoTask; isActive: boolean }) {
  const tint = STATUS_TINT[task.status];
  const line1 =
    task.status === "queued"
      ? `排队中 · 前方还有 ${(task.queue_position ?? 1) - 1} 个任务`
      : task.status === "running"
        ? `生成中 · ${task.stage ? `${STAGE_LABEL[task.stage]}阶段 · ` : ""}${formatPercent(task.progress)}`
        : task.status === "done"
          ? "已完成 · 可播放"
          : `失败 · ${task.error ?? "未知错误"}`;

  return (
    <li
      style={{
        display: "flex",
        gap: "var(--space-12)",
        alignItems: "flex-start",
        padding: "var(--space-12) 0",
        borderBottom: "var(--border-width) solid var(--nb-border)",
        backgroundColor: isActive ? "var(--nb-bg-hover)" : "transparent",
      }}
    >
      <span
        className="flex items-center justify-center"
        style={{
          width: 32,
          height: 32,
          flexShrink: 0,
          borderRadius: "var(--nb-radius-sm)",
          backgroundColor: tint.bg,
          color: tint.ink,
        }}
      >
        <Icon name={tint.icon} size={16} style={task.status === "running" ? { animation: "nb-spin 1s linear infinite" } : undefined} />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between" style={{ gap: "var(--space-8)" }}>
          <span style={{ fontSize: "var(--text-body-size)", fontWeight: 500, color: "var(--nb-text)" }}>
            视频任务 #{task.id}
            {isActive ? " · 当前" : ""}
          </span>
          <span
            className="flex items-center"
            style={{ gap: 4, fontSize: "var(--text-micro-label-size)", fontWeight: 500, letterSpacing: "var(--text-micro-label-letter-spacing)", color: tint.ink, flexShrink: 0 }}
          >
            <span
              aria-hidden="true"
              style={{ width: 6, height: 6, borderRadius: "var(--nb-radius-pill)", backgroundColor: tint.ink }}
            />
            {STATUS_LABEL[task.status]}
          </span>
        </div>
        <div style={{ marginTop: 2, fontSize: "var(--text-meta-size)", color: "var(--nb-text-tertiary)" }}>{line1}</div>
        {task.status === "running" ? (
          <div
            role="progressbar"
            aria-valuenow={Math.round(task.progress * 100)}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={`任务 #${task.id} 合成进度`}
            style={{ marginTop: "var(--space-8)", height: 4, borderRadius: "var(--nb-radius-pill)", backgroundColor: "var(--nb-bg-subtle)", overflow: "hidden" }}
          >
            <div
              style={{
                width: `${Math.min(100, Math.round(task.progress * 100))}%`,
                height: "100%",
                backgroundColor: "var(--nb-accent)",
                transition: "width var(--duration-normal) var(--ease-out)",
              }}
            />
          </div>
        ) : null}
        {task.status === "done" && task.video_url ? (
          <a
            href={task.video_url}
            download
            className="flex items-center"
            style={{ marginTop: "var(--space-8)", fontSize: "var(--text-meta-size)", color: "var(--nb-accent)", gap: 4, textDecoration: "none" }}
          >
            <Icon name="play" size={16} />
            播放 / 下载视频
          </a>
        ) : null}
      </div>
    </li>
  );
}
