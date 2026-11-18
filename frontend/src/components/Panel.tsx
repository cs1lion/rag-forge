/**
 * 面板容器：白底 + 1px 描边 + 12px 圆角，无阴影（DESIGN.md §5/§6）。
 */
import type { ReactNode } from "react";

interface PanelProps {
  title: string;
  meta?: string;
  children: ReactNode;
  className?: string;
}

export function Panel({ title, meta, children, className = "" }: PanelProps) {
  return (
    <section
      className={`flex min-h-0 flex-col rounded-md ${className}`}
      style={{
        backgroundColor: "var(--nb-bg)",
        border: "var(--border-width) solid var(--nb-border)",
      }}
    >
      <div
        className="flex items-baseline justify-between"
        style={{ padding: "var(--space-16) var(--space-16) var(--space-8)" }}
      >
        <h2
          style={{
            fontSize: "var(--text-section-title-size)",
            lineHeight: "var(--text-section-title-line-height)",
            fontWeight: "var(--text-section-title-weight)",
            color: "var(--nb-text)",
          }}
        >
          {title}
        </h2>
        {meta ? (
          <span
            style={{
              fontSize: "var(--text-meta-size)",
              lineHeight: "var(--text-meta-line-height)",
              color: "var(--nb-text-tertiary)",
            }}
          >
            {meta}
          </span>
        ) : null}
      </div>
      <div className="min-h-0 flex-1">{children}</div>
    </section>
  );
}
