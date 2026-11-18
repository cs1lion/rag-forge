/**
 * 历史问答记录列表（Step 2）：点击回看历史问答、引用与视频；
 * 行内显示关联视频状态徽标（文字 + 图标，不只用颜色，DESIGN.md §3）。
 */
import { Icon } from "./Icon";
import type { QaRecordSummary, VideoTaskStatus } from "../types";
import { formatDate, formatTime } from "../lib/format";

interface HistoryListProps {
  records: QaRecordSummary[];
  selectedId: number | null;
  onSelect: (id: number) => Promise<void>;
}

const STATUS_LABEL: Record<Exclude<VideoTaskStatus, null>, string> = {
  queued: "排队中",
  running: "生成中",
  done: "可播放",
  failed: "失败",
};

export function HistoryList({ records, selectedId, onSelect }: HistoryListProps) {
  return (
    <ul role="list" aria-label="历史问答" style={{ padding: "0 var(--space-8) var(--space-8)" }}>
      {records.length === 0 ? (
        <li
          style={{
            padding: "var(--space-12) var(--space-8)",
            fontSize: "var(--text-body-size)",
            color: "var(--nb-text-tertiary)",
          }}
        >
          还没有问答记录，提出第一个问题后会自动保存在这里。
        </li>
      ) : (
        records.map((rec) => {
          const active = rec.id === selectedId;
          return (
            <li key={rec.id}>
              <button
                type="button"
                onClick={() => void onSelect(rec.id)}
                aria-current={active ? "true" : undefined}
                className="flex w-full items-start transition-colors"
                style={{
                  width: "100%",
                  minHeight: 40,
                  padding: "var(--space-8)",
                  gap: "var(--space-8)",
                  textAlign: "left",
                  borderRadius: "var(--nb-radius-sm)",
                  backgroundColor: active ? "var(--nb-bg-hover)" : "transparent",
                }}
              >
                <Icon
                  name="history"
                  size={16}
                  style={{ color: "var(--nb-text-tertiary)", flexShrink: 0, marginTop: 2 }}
                />
                <span className="min-w-0 flex-1">
                  <span
                    style={{
                      display: "block",
                      fontSize: "var(--text-body-size)",
                      color: active ? "var(--nb-text)" : "var(--nb-text-secondary)",
                      whiteSpace: "nowrap",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                    }}
                  >
                    {rec.question}
                  </span>
                  <span
                    className="flex items-center"
                    style={{
                      marginTop: 2,
                      gap: "var(--space-8)",
                      fontSize: "var(--text-meta-size)",
                      color: "var(--nb-text-tertiary)",
                    }}
                  >
                    <span>
                      {formatDate(rec.created_at)} {formatTime(rec.created_at)}
                    </span>
                    {rec.video_status ? (
                      <span className="flex items-center" style={{ gap: 4 }}>
                        <VideoStatusDot status={rec.video_status} />
                        {STATUS_LABEL[rec.video_status]}
                      </span>
                    ) : null}
                  </span>
                </span>
              </button>
            </li>
          );
        })
      )}
    </ul>
  );
}

/** 状态圆点：颜色是信号之一，始终配文字（DESIGN.md §3 规则） */
function VideoStatusDot({ status }: { status: VideoTaskStatus }) {
  const map: Record<VideoTaskStatus, { bg: string; ink: string }> = {
    queued: { bg: "var(--nb-tint-amber-bg)", ink: "var(--nb-tint-amber-ink)" },
    running: { bg: "var(--nb-tint-blue-bg)", ink: "var(--nb-tint-blue-ink)" },
    done: { bg: "var(--nb-tint-green-bg)", ink: "var(--nb-tint-green-ink)" },
    failed: { bg: "var(--nb-tint-amber-bg)", ink: "var(--nb-tint-amber-ink)" },
  };
  return (
    <span
      aria-hidden="true"
      style={{
        width: 8,
        height: 8,
        borderRadius: "var(--nb-radius-pill)",
        backgroundColor: map[status].bg,
        boxShadow: `inset 0 0 0 1px ${map[status].ink}`,
        flexShrink: 0,
      }}
    />
  );
}
