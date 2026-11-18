/**
 * 答案区（Step 3）：SSE 检索/生成阶段状态 + 流式正文 + 拒答/错误态。
 * 空状态、加载态、错误态均为完整句子（DESIGN.md §8）。
 */
import { Icon } from "./Icon";
import type { QaProgressState } from "../hooks/useWorkbench";

interface AnswerViewProps {
  question: string;
  answer: string;
  progress: QaProgressState | null;
  isAsking: boolean;
  refusalReason: string | null;
  confidence: number | null;
  error: string | null;
}

const STAGE_LABEL = { retrieval: "检索阶段", generation: "生成阶段" } as const;

export function AnswerView({ question, answer, progress, isAsking, refusalReason, confidence, error }: AnswerViewProps) {
  return (
    <div className="flex flex-col" style={{ gap: "var(--space-16)", minHeight: 200 }}>
      {question ? (
        <div>
          <div
            style={{
              fontSize: "var(--text-micro-label-size)",
              lineHeight: "var(--text-micro-label-line-height)",
              fontWeight: "var(--text-micro-label-weight)",
              letterSpacing: "var(--text-micro-label-letter-spacing)",
              color: "var(--nb-text-tertiary)",
              marginBottom: "var(--space-4)",
            }}
          >
            问题
          </div>
          <p style={{ fontSize: "var(--text-card-title-size-zh)", fontWeight: 500, color: "var(--nb-text)", lineHeight: 1.45 }}>
            {question}
          </p>
        </div>
      ) : null}

      {error ? (
        <div
          role="alert"
          className="flex items-start"
          style={{
            gap: "var(--space-8)",
            padding: "var(--space-16)",
            border: "var(--border-width) solid var(--nb-border)",
            borderRadius: "var(--nb-radius-md)",
            backgroundColor: "var(--nb-bg-subtle)",
            color: "var(--nb-tint-amber-ink)",
            fontSize: "var(--text-body-size)",
          }}
        >
          <Icon name="alert" size={16} style={{ marginTop: 3, flexShrink: 0 }} />
          <span>{error}</span>
        </div>
      ) : null}

      {progress && isAsking ? (
        <div className="flex items-center" style={{ gap: "var(--space-12)" }}>
          <Icon name="spinner" size={16} style={{ color: "var(--nb-accent)", animation: "nb-spin 1s linear infinite" }} />
          <span style={{ fontSize: "var(--text-body-size)", color: "var(--nb-text-secondary)" }}>
            {STAGE_LABEL[progress.stage]}：{progress.message}
            {typeof progress.progress === "number" ? `（${Math.round(progress.progress * 100)}%）` : ""}
          </span>
        </div>
      ) : null}

      {refusalReason ? (
        <div
          className="flex items-start"
          style={{
            gap: "var(--space-8)",
            padding: "var(--space-16)",
            border: "var(--border-width) solid var(--nb-border)",
            borderRadius: "var(--nb-radius-md)",
            backgroundColor: "var(--nb-bg-subtle)",
          }}
        >
          <Icon name="alert" size={16} style={{ color: "var(--nb-tint-amber-ink)", marginTop: 3, flexShrink: 0 }} />
          <div>
            <p style={{ fontSize: "var(--text-body-size)", color: "var(--nb-text-secondary)", margin: 0 }}>{answer || "文档未给出确定数值，无法回答该问题。"}</p>
            <p style={{ fontSize: "var(--text-meta-size)", color: "var(--nb-text-tertiary)", margin: "var(--space-8) 0 0" }}>
              拒答原因：{refusalReason}
            </p>
          </div>
        </div>
      ) : answer ? (
        <p
          style={{
            margin: 0,
            fontSize: "var(--text-body-size-zh, 15px)",
            lineHeight: 1.75,
            color: "var(--nb-text-secondary)",
            whiteSpace: "pre-wrap",
          }}
        >
          {answer}
          {isAsking ? <span style={{ color: "var(--nb-accent)" }}>▍</span> : null}
        </p>
      ) : !isAsking && !error ? (
        <p style={{ fontSize: "var(--text-body-size)", color: "var(--nb-text-tertiary)", margin: 0 }}>
          在上方输入问题并点击「提问」，系统将基于已入库文档作答，并附上引用来源与视频生成进度。
        </p>
      ) : null}

      {typeof confidence === "number" && !refusalReason ? (
        <div style={{ fontSize: "var(--text-meta-size)", color: "var(--nb-text-tertiary)" }}>
          可信度 {(confidence * 100).toFixed(0)}%
        </div>
      ) : null}

      <style>{`@keyframes nb-spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
