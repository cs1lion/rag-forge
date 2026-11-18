/**
 * 中栏问答主区（Step 3）：max-width 720px 居中；
 * 提问入口 → 引用来源卡片 → 答案正文。
 */
import { QuestionBox } from "./QuestionBox";
import { SourcesBar } from "./SourcesBar";
import { AnswerView } from "./AnswerView";
import type { Citation } from "../types";
import type { QaProgressState } from "../hooks/useWorkbench";

interface MainPanelProps {
  question: string;
  answer: string;
  citations: Citation[];
  progress: QaProgressState | null;
  isAsking: boolean;
  refusalReason: string | null;
  confidence: number | null;
  error: string | null;
  onAsk: (q: string) => void;
  examples: string[];
}

export function MainPanel(props: MainPanelProps) {
  return (
    <div style={{ width: "100%", maxWidth: 720, display: "flex", flexDirection: "column", gap: "var(--space-24)" }}>
      <QuestionBox onAsk={props.onAsk} disabled={props.isAsking} examples={props.examples} />

      <div
        style={{
          backgroundColor: "var(--nb-bg)",
          border: "var(--border-width) solid var(--nb-border)",
          borderRadius: "var(--nb-radius-md)",
          padding: "var(--space-20)",
          display: "flex",
          flexDirection: "column",
          gap: "var(--space-20)",
        }}
      >
        {props.question ? (
          <>
            <SourcesBar citations={props.citations} />
            <AnswerView
              question={props.question}
              answer={props.answer}
              progress={props.progress}
              isAsking={props.isAsking}
              refusalReason={props.refusalReason}
              confidence={props.confidence}
              error={props.error}
            />
          </>
        ) : (
          <AnswerView
            question=""
            answer=""
            progress={null}
            isAsking={false}
            refusalReason={null}
            confidence={null}
            error={null}
          />
        )}
      </div>
    </div>
  );
}
