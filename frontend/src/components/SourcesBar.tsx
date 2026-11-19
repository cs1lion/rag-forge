/**
 * 引用来源卡片（Step 3）：答案正文上方的横向 Sources 条。
 * 卡片 = 色块图标（32×32，8px 圆角，成对 tint）+ 文档名 + 章节路径 + 箭头；
 * 点击展开详情：文档名、章节路径 heading_path、段落定位 para_id、原文段落与相似度。
 * 四维溯源：doc_id + source_file + heading_path + para_id（CLAUDE.md §三.4）。
 */
import { useState } from "react";
import { Icon } from "./Icon";
import type { Citation, RiskWarning } from "../types";
import { formatDate } from "../lib/format";

interface SourcesBarProps {
  citations: Citation[];
  /** 涉及文档的风险提示汇总（qa.citations 事件下发，§6） */
  riskWarnings?: RiskWarning[];
  createdAt?: string;
}

export function SourcesBar({ citations, riskWarnings = [], createdAt }: SourcesBarProps) {
  const [selected, setSelected] = useState<number | null>(null);

  if (citations.length === 0 && riskWarnings.length === 0) return null;

  const active = selected !== null ? citations[selected] : null;
  // 入库时自动识别到越权指令文本的文档：在检索结果中提示风险
  const riskyCitations = citations.filter((c) => c.injection_flag === 1);

  return (
    <section aria-label="引用来源" style={{ display: "flex", flexDirection: "column", gap: "var(--space-12)" }}>
      <div
        className="flex items-center justify-between"
        style={{ fontSize: "var(--text-meta-size)", color: "var(--nb-text-tertiary)" }}
      >
        <span>
          {citations.length} 个来源{createdAt ? ` · ${formatDate(createdAt)}` : ""}
        </span>
        <span>点击卡片查看原文段落</span>
      </div>

      {riskyCitations.length > 0 || riskWarnings.length > 0 ? (
        <div
          role="alert"
          className="flex items-start"
          style={{
            gap: "var(--space-8)",
            padding: "var(--space-12) var(--space-16)",
            border: "var(--border-width) solid var(--nb-border)",
            borderRadius: "var(--nb-radius-sm)",
            backgroundColor: "var(--nb-tint-amber-bg)",
            color: "var(--nb-tint-amber-ink)",
          }}
        >
          <Icon name="alert" size={16} style={{ marginTop: 2, flexShrink: 0 }} />
          <span style={{ fontSize: "var(--text-meta-size)", lineHeight: "var(--text-body-line-height)" }}>
            {riskWarnings.length > 0
              ? `风险提示：${riskWarnings.map((w) => `${w.source_file}（${w.risk_warning}）`).join("；")}`
              : `以下 ${riskyCitations.length} 个来源来自含疑似越权指令文本的文档` +
                "（入库时已自动识别并过滤相关段落，不参与检索），回答已按双重防注入机制处理，请留意引用内容：" +
                riskyCitations.map((c) => c.source_file).join("、")}
          </span>
        </div>
      ) : null}

      <div
        className="flex"
        style={{ gap: "var(--space-8)", overflowX: "auto", paddingBottom: "var(--space-4)" }}
        role="listbox"
        aria-label="引用来源卡片"
      >
        {citations.map((cit, i) => {
          const isActive = selected === i;
          const sourceFile = cit.source_file || cit.filename || "原始文件名已不可用";
          const headingPath = cit.heading_path || "章节路径未记录";
          return (
            <button
              key={`${cit.para_id}-${i}`}
              type="button"
              role="option"
              aria-selected={isActive}
              onClick={() => setSelected(isActive ? null : i)}
              className="flex min-w-0 transition-colors"
              style={{
                width: 240,
                flexShrink: 0,
                padding: "var(--space-12)",
                gap: "var(--space-12)",
                border: "var(--border-width) solid var(--nb-border)",
                borderRadius: "var(--nb-radius-md)",
                backgroundColor: isActive ? "var(--nb-accent-soft)" : "var(--nb-bg)",
                textAlign: "left",
                cursor: "pointer",
              }}
            >
              <span
                className="flex items-center justify-center"
                style={{
                  width: 32,
                  height: 32,
                  flexShrink: 0,
                  borderRadius: "var(--nb-radius-sm)",
                  backgroundColor: "var(--nb-tint-blue-bg)",
                  color: "var(--nb-tint-blue-ink)",
                }}
              >
                <Icon name="file" size={16} />
              </span>
              <span className="min-w-0 flex-1">
                <span
                  style={{
                    display: "block",
                    fontSize: "var(--text-body-size)",
                    fontWeight: 500,
                    lineHeight: "var(--text-body-line-height)",
                    color: "var(--nb-text)",
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                  }}
                >
                  {sourceFile}
                </span>
                <span
                  style={{
                    display: "block",
                    marginTop: 2,
                    fontSize: "var(--text-meta-size)",
                    lineHeight: "var(--text-meta-line-height)",
                    color: "var(--nb-text-tertiary)",
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                  }}
                >
                  {headingPath}
                </span>
              </span>
              <Icon
                name={isActive ? "chevron-down" : "chevron-right"}
                size={16}
                style={{ color: "var(--nb-text-tertiary)", flexShrink: 0, alignSelf: "center" }}
              />
            </button>
          );
        })}
      </div>

      {active ? (
        <div
          className="flex flex-col"
          style={{
            gap: "var(--space-8)",
            padding: "var(--space-16)",
            border: "var(--border-width) solid var(--nb-border)",
            borderRadius: "var(--nb-radius-md)",
            backgroundColor: "var(--nb-bg)",
          }}
        >
          <div className="flex flex-wrap items-baseline" style={{ gap: "var(--space-12)" }}>
            <span style={{ fontSize: "var(--text-card-title-size-zh)", fontWeight: 500, color: "var(--nb-text)" }}>
              {active.doc_title || active.filename || active.source_file || "原文档已删除"}
            </span>
            <span style={{ fontSize: "var(--text-meta-size)", color: "var(--nb-text-tertiary)" }}>
              原文文件：{active.source_file || active.filename || "原始文件名已不可用"}
            </span>
            <span style={{ fontSize: "var(--text-meta-size)", color: "var(--nb-text-tertiary)" }}>
              语料编号：{active.doc_id || "未记录"}
            </span>
            <span style={{ fontSize: "var(--text-meta-size)", color: "var(--nb-text-tertiary)" }}>
              相似度 {((active.score ?? 0) * 100).toFixed(0)}%
            </span>
          </div>
          <div style={{ fontSize: "var(--text-meta-size)", color: "var(--nb-text-tertiary)" }}>
            章节路径：{active.heading_path || "章节路径未记录"}
          </div>
          <div style={{ fontSize: "var(--text-meta-size)", color: "var(--nb-text-tertiary)" }}>
            段落定位：{active.para_id || "段落编号未记录"}
          </div>
          <blockquote
            style={{
              margin: 0,
              padding: "var(--space-12) var(--space-16)",
              backgroundColor: "var(--nb-bg-subtle)",
              border: "var(--border-width) solid var(--nb-border)",
              borderRadius: "var(--nb-radius-sm)",
              fontSize: "var(--text-body-size)",
              color: "var(--nb-text-secondary)",
              lineHeight: "var(--text-body-line-height)",
            }}
          >
            {active.snippet}
          </blockquote>
        </div>
      ) : null}
    </section>
  );
}
