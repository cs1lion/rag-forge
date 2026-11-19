/**
 * 历史问答弹层（会话 4）：右上角历史按钮点击后弹出。
 * 列表长度自适应页面高度，超出部分内部滚动；
 * 点击条目回看（主页中间+右侧切换为详情与产物），支持删除。
 */
import { Icon } from "./Icon";
import type { QaRecordSummary, VideoTaskStatus } from "../types";
import { formatDate, formatTime } from "../lib/format";

/** 视频状态中文文案（DESIGN.md §3：不得只用颜色，需有文字） */
const VIDEO_STATUS_LABEL: Record<NonNullable<VideoTaskStatus>, string> = {
  queued: "视频排队中",
  running: "视频生成中",
  done: "视频可播放",
  failed: "视频生成失败",
  skipped: "未生成视频",
};

interface HistoryDrawerProps {
  open: boolean;
  records: QaRecordSummary[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  onDelete: (id: number) => void;
  onClose: () => void;
}

export function HistoryDrawer(props: HistoryDrawerProps) {
  if (!props.open) return null;

  return (
    <div
      className="fixed inset-0 z-40 flex justify-end"
      style={{ backgroundColor: "rgba(31, 31, 31, 0.16)" }}
      onClick={props.onClose}
    >
      <aside
        role="dialog"
        aria-label="历史问答"
        className="flex min-h-0 flex-col"
        style={{
          width: 400,
          maxWidth: "90vw",
          height: "100%",
          backgroundColor: "var(--nb-bg)",
          borderLeft: "var(--border-width) solid var(--nb-border)",
          boxShadow: "0 1px 2px rgba(0,0,0,.04), 0 8px 24px rgba(0,0,0,.08)",
          padding: "var(--space-16)",
          gap: "var(--space-12)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div
          className="flex items-center justify-between"
          style={{ paddingBottom: "var(--space-12)", borderBottom: "var(--border-width) solid var(--nb-border)" }}
        >
          <h2
            style={{
              fontSize: "var(--text-section-title-size)",
              lineHeight: "var(--text-section-title-line-height)",
              fontWeight: "var(--text-section-title-weight)",
              color: "var(--nb-text)",
            }}
          >
            历史问答
          </h2>
          <button
            type="button"
            aria-label="关闭历史问答"
            onClick={props.onClose}
            className="flex items-center justify-center rounded-full transition-colors"
            style={{ width: 32, height: 32 }}
            onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = "var(--nb-bg-hover)")}
            onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = "transparent")}
          >
            <Icon name="close" size={16} style={{ color: "var(--nb-text-secondary)" }} />
          </button>
        </div>

        <ul
          role="list"
          aria-label="历史问答列表"
          className="min-h-0 flex-1 overflow-y-auto"
          style={{ margin: 0, padding: 0, listStyle: "none" }}
        >
          {props.records.length === 0 ? (
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
            props.records.map((rec) => {
              const active = rec.id === props.selectedId;
              return (
                <li
                  key={rec.id}
                  className="group flex items-start"
                  style={{
                    gap: "var(--space-8)",
                    padding: "var(--space-12) var(--space-8)",
                    borderRadius: "var(--nb-radius-sm)",
                    backgroundColor: active ? "var(--nb-bg-hover)" : "transparent",
                  }}
                >
                  <button
                    type="button"
                    onClick={() => props.onSelect(rec.id)}
                    className="flex min-w-0 flex-1 items-start text-left"
                    aria-current={active ? "true" : undefined}
                  >
                    <Icon
                      name="history"
                      size={16}
                      style={{ color: "var(--nb-text-tertiary)", flexShrink: 0, marginTop: 3 }}
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
                        {rec.video_status ? <span>· {VIDEO_STATUS_LABEL[rec.video_status]}</span> : null}
                      </span>
                    </span>
                  </button>
                  <button
                    type="button"
                    aria-label={`删除历史问答 ${rec.id}`}
                    onClick={() => props.onDelete(rec.id)}
                    className="flex items-center justify-center rounded-full opacity-0 transition-opacity group-hover:opacity-100 focus:opacity-100"
                    style={{ width: 28, height: 28, flexShrink: 0 }}
                    onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = "var(--nb-bg)")}
                    onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = "transparent")}
                  >
                    <Icon name="trash" size={16} style={{ color: "var(--nb-text-tertiary)" }} />
                  </button>
                </li>
              );
            })
          )}
        </ul>

        <div style={{ fontSize: "var(--text-meta-size)", color: "var(--nb-text-tertiary)" }}>
          共 {props.records.length} 条记录
        </div>
      </aside>
    </div>
  );
}
