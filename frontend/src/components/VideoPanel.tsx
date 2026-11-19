/**
 * 视频工作室（Step 4）：当前问答的 MP4 播放器 + 下方视频任务队列面板。
 * 队列严格按 DESIGN.md §3 成对功能色块 + 线性图标展示四种状态。
 * 全局单并发：running_count ≤ 1（API_SPEC §6.2）。
 * 列表长度自适应页面高度，超出部分内部滚动（不撑长页面）。
 *
 * 播放语义：播放器始终在页面内在线播放（inline）；下载是独立的功能按钮，
 * 不与播放混淆；每个任务行提供「在线播放」「下载」两个独立操作。
 */
import { Icon } from "./Icon";
import type { VideoTask } from "../types";
import { formatPercent } from "../lib/format";

interface VideoPanelProps {
  tasks: VideoTask[];
  runningCount: number;
  activeTaskId: number | null;
  onDeleteTask: (taskId: number) => void;
  onPlayTask: (taskId: number) => void;
}

/** 成对功能色块：底浅一档、墨深一档（DESIGN.md §3） */
const STATUS_TINT: Record<VideoTask["status"], { bg: string; ink: string; icon: "queue" | "spinner" | "play" | "alert" | "film" }> = {
  queued: { bg: "var(--nb-tint-amber-bg)", ink: "var(--nb-tint-amber-ink)", icon: "queue" },
  running: { bg: "var(--nb-tint-blue-bg)", ink: "var(--nb-tint-blue-ink)", icon: "spinner" },
  done: { bg: "var(--nb-tint-green-bg)", ink: "var(--nb-tint-green-ink)", icon: "play" },
  failed: { bg: "var(--nb-tint-amber-bg)", ink: "var(--nb-tint-amber-ink)", icon: "alert" },
  skipped: { bg: "var(--nb-bg-hover)", ink: "var(--nb-text-tertiary)", icon: "film" },
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
  skipped: "已跳过",
};

export function VideoPanel({ tasks, runningCount, activeTaskId, onDeleteTask, onPlayTask }: VideoPanelProps) {
  const active = tasks.find((t) => t.id === activeTaskId) ?? null;
  const activePlayable = active?.status === "done" && !!active.video_url;

  return (
    <div className="flex min-h-0 flex-1 flex-col" style={{ gap: "var(--space-16)" }}>
      {/* 当前问答视频（在线播放） */}
      <section aria-label="当前问答视频">
        {activePlayable ? (
          <div>
            <video
              controls
              playsInline
              preload="metadata"
              src={active.video_url ?? undefined}
              style={{ width: "100%", height: "auto", borderRadius: "var(--nb-radius-md)", border: "var(--border-width) solid var(--nb-border)", backgroundColor: "var(--nb-text)" }}
            >
              您的浏览器不支持视频播放，可点击下方按钮下载后观看。
            </video>
            <div className="flex items-center justify-between" style={{ marginTop: "var(--space-8)" }}>
              <span style={{ fontSize: "var(--text-meta-size)", color: "var(--nb-text-tertiary)" }}>
                视频任务 #{active.id} · 在线播放
              </span>
              <a
                href={active.video_url ?? undefined}
                download={`qa_video_${active.id}.mp4`}
                aria-label={`下载当前视频 ${active.id}`}
                className="flex items-center"
                style={{ fontSize: "var(--text-meta-size)", color: "var(--nb-accent)", gap: 4, textDecoration: "none" }}
              >
                <Icon name="download" size={16} />
                下载
              </a>
            </div>
          </div>
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
                    : active?.status === "skipped"
                      ? "该问题未命中知识库，已跳过视频生成"
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
        className="min-h-0 flex-1 overflow-y-auto"
        style={{ margin: 0, padding: 0, listStyle: "none", borderTop: "var(--border-width) solid var(--nb-border)" }}
      >
        {tasks.length === 0 ? (
          <li style={{ fontSize: "var(--text-body-size)", color: "var(--nb-text-tertiary)", padding: "var(--space-12) 0" }}>
            暂无视频任务，提出第一个问题后自动创建。
          </li>
        ) : (
          tasks.map((task) => (
            <VideoTaskRow
              key={task.id}
              task={task}
              isActive={task.id === activeTaskId}
              onDelete={onDeleteTask}
              onPlay={onPlayTask}
            />
          ))
        )}
      </ul>
    </div>
  );
}

/** 生成物条目样式（DESIGN.md §6）：色块图标 + 标题 + 一行说明，条目间 1px 分隔线，不加卡片外框 */
function VideoTaskRow({
  task,
  isActive,
  onDelete,
  onPlay,
}: {
  task: VideoTask;
  isActive: boolean;
  onDelete: (taskId: number) => void;
  onPlay: (taskId: number) => void;
}) {
  const tint = STATUS_TINT[task.status];
  const line1 =
    task.status === "queued"
      ? `排队中 · 前方还有 ${(task.queue_position ?? 1) - 1} 个任务`
      : task.status === "running"
        ? `生成中 · ${task.stage ? `${STAGE_LABEL[task.stage]}阶段 · ` : ""}${formatPercent(task.progress)}`
        : task.status === "done"
          ? "已完成 · 可在线播放"
          : task.status === "skipped"
            ? "未生成 · 知识库未命中"
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
        <div className="flex items-center" style={{ marginTop: "var(--space-8)", gap: "var(--space-8)" }}>
          {task.status === "done" && task.video_url ? (
            <>
              <button
                type="button"
                aria-label={`在线播放视频 ${task.id}`}
                onClick={() => onPlay(task.id)}
                className="flex items-center rounded-sm transition-colors"
                style={{
                  height: 26,
                  padding: "0 10px",
                  gap: 4,
                  border: "var(--border-width) solid var(--nb-border)",
                  backgroundColor: "var(--nb-bg)",
                  color: "var(--nb-accent)",
                  fontSize: "var(--text-meta-size)",
                  cursor: "pointer",
                }}
                onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = "var(--nb-bg-hover)")}
                onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = "var(--nb-bg)")}
              >
                <Icon name="play" size={16} />
                在线播放
              </button>
              <a
                href={task.video_url}
                download={`qa_video_${task.id}.mp4`}
                aria-label={`下载视频 ${task.id}`}
                className="flex items-center rounded-sm transition-colors"
                style={{
                  height: 26,
                  padding: "0 10px",
                  gap: 4,
                  border: "var(--border-width) solid var(--nb-border)",
                  backgroundColor: "var(--nb-bg)",
                  color: "var(--nb-text-secondary)",
                  fontSize: "var(--text-meta-size)",
                  textDecoration: "none",
                }}
              >
                <Icon name="download" size={16} />
                下载
              </a>
            </>
          ) : null}
          <button
            type="button"
            aria-label={`删除视频任务 ${task.id}`}
            disabled={task.status === "running"}
            onClick={() => onDelete(task.id)}
            className="flex items-center justify-center rounded-full transition-colors"
            style={{
              width: 28,
              height: 28,
              marginLeft: "auto",
              cursor: task.status === "running" ? "not-allowed" : "pointer",
              opacity: task.status === "running" ? 0.4 : 1,
            }}
            title={task.status === "running" ? "任务合成中，完成后才能删除" : "删除该视频任务"}
            onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = "var(--nb-bg-hover)")}
            onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = "transparent")}
          >
            <Icon name="trash" size={16} style={{ color: "var(--nb-text-tertiary)" }} />
          </button>
        </div>
      </div>
    </li>
  );
}
