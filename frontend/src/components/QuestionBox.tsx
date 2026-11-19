/**
 * 提问入口（Step 3）：居中搜索框式输入 + 快捷示例问题。
 * 输入框 --nb-bg-subtle 底、8px 圆角、聚焦 2px 强调色环；
 * 提交为次按钮（白底描边）——实心主按钮仅顶栏「+ 创建」一个（DESIGN.md §6）。
 */
import { useState } from "react";
import { Icon } from "./Icon";

interface QuestionBoxProps {
  onAsk: (question: string) => void;
  disabled: boolean;
  /** 文档库有文档但全部取消勾选时，禁止发送并展示固定提示 */
  noDocSelected?: boolean;
  examples: string[];
}

export function QuestionBox({ onAsk, disabled, noDocSelected = false, examples }: QuestionBoxProps) {
  const [value, setValue] = useState("");
  const selectionBlocked = noDocSelected && !disabled;
  const cannotSubmit = disabled || noDocSelected || !value.trim();

  const submit = () => {
    if (cannotSubmit) return;
    onAsk(value);
    setValue("");
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-12)" }}>
      <div
        className="nb-input flex items-center"
        style={{
          gap: "var(--space-12)",
          backgroundColor: "var(--nb-bg-subtle)",
          borderRadius: "var(--nb-radius-sm)",
          padding: "0 var(--space-16)",
          height: 48,
        }}
      >
        <Icon name="search" size={20} style={{ color: "var(--nb-text-tertiary)", flexShrink: 0 }} />
        <input
          type="text"
          value={value}
          disabled={disabled}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") submit();
          }}
          placeholder="基于知识库提问，答案将附引用溯源…"
          aria-label="提问"
          aria-describedby={selectionBlocked ? "question-doc-selection-hint" : undefined}
          className="min-w-0 flex-1 bg-transparent outline-none"
          style={{
            fontSize: "var(--text-body-size-zh, 15px)",
            color: "var(--nb-text)",
          }}
        />
        <button
          type="button"
          onClick={submit}
          disabled={cannotSubmit}
          className="rounded-sm transition-colors"
          style={{
            height: 32,
            padding: "0 var(--space-16)",
            border: "var(--border-width) solid var(--nb-border-strong)",
            backgroundColor: "var(--nb-bg)",
            color: value.trim() ? "var(--nb-text)" : "var(--nb-text-tertiary)",
            fontSize: "var(--text-body-size)",
            fontWeight: 500,
            cursor: cannotSubmit ? "not-allowed" : "pointer",
          }}
          onMouseEnter={(e) => {
            if (!cannotSubmit) e.currentTarget.style.backgroundColor = "var(--nb-bg-hover)";
          }}
          onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = "var(--nb-bg)")}
        >
          提问
        </button>
      </div>

      {selectionBlocked ? (
        <p
          id="question-doc-selection-hint"
          role="note"
          style={{ margin: 0, fontSize: "var(--text-meta-size)", color: "var(--nb-text-tertiary)" }}
        >
          请至少勾选 1 份知识库文档
        </p>
      ) : null}

      {examples.length > 0 ? (
        <div className="flex flex-wrap items-center" style={{ gap: "var(--space-8)" }}>
          <span
            style={{
              fontSize: "var(--text-micro-label-size)",
              lineHeight: "var(--text-micro-label-line-height)",
              fontWeight: "var(--text-micro-label-weight)",
              letterSpacing: "var(--text-micro-label-letter-spacing)",
              color: "var(--nb-text-tertiary)",
            }}
          >
            示例问题
          </span>
          {examples.map((q) => (
            <button
              key={q}
              type="button"
              disabled={disabled}
              onClick={() => onAsk(q)}
              className="rounded-pill transition-colors"
              style={{
                height: 28,
                padding: "0 var(--space-12)",
                border: "var(--border-width) solid var(--nb-border)",
                backgroundColor: "var(--nb-bg)",
                color: "var(--nb-text-secondary)",
                fontSize: "var(--text-meta-size)",
                cursor: disabled ? "not-allowed" : "pointer",
              }}
              onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = "var(--nb-bg-hover)")}
              onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = "var(--nb-bg)")}
            >
              {q}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
