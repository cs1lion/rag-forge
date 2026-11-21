import React, { useState } from "react";

export interface ScoreBreakdown {
  fts: number;
  vector: number;
  rrf: number;
}

export interface EvidenceCitation {
  doc_id: string;
  source_file: string;
  heading_path?: string;
  para_id: string;
  snippet?: string;
  text?: string;
  score?: number;
  score_breakdown?: ScoreBreakdown;
}

export interface VerificationReport {
  faithfulness_score: number;
  total_claims: number;
  supported_claims: number;
  unsupported_claims: Array<{ claim: string; reason: string; overlap: number }>;
}

interface EvidenceXRayProps {
  citations: EvidenceCitation[];
  verification?: VerificationReport | null;
  onSelectCitation?: (citation: EvidenceCitation) => void;
}

/**
 * 工作室级检索证据透视面板（严格遵循 DESIGN.md：白底、1px 描边、无阴影、配对语义浅底色块）。
 * 支持展开查看每条引用的 FTS5 词法分、向量语义分、RRF 融合分与原文全文预览。
 */
export const EvidenceXRay: React.FC<EvidenceXRayProps> = ({
  citations,
  verification,
  onSelectCitation,
}) => {
  const [expanded, setExpanded] = useState(false);
  const [activeParaId, setActiveParaId] = useState<string | null>(null);

  if (!citations.length) {
    return null;
  }

  const maxFts = Math.max(
    ...citations.map((c) => c.score_breakdown?.fts ?? 0),
    0.01
  );

  return (
    <section
      aria-label="检索证据透视"
      className="nb-fade-in"
      style={{
        width: "100%",
        maxWidth: 720,
        marginTop: "var(--space-16)",
        padding: "var(--space-16)",
        backgroundColor: "var(--nb-bg-subtle)",
        border: "var(--border-width, 1px) solid var(--nb-border)",
        borderRadius: "var(--nb-radius-md, 12px)",
      }}
    >
      <div
        className="flex items-center justify-between"
        style={{ gap: "var(--space-8)" }}
      >
        <div className="flex items-center" style={{ gap: "var(--space-8)" }}>
          <span
            style={{
              fontSize: "var(--text-card-title-size, 15px)",
              fontWeight: 500,
              color: "var(--nb-text)",
            }}
          >
            证据透视 X-Ray
          </span>
          <span
            className="nb-pill"
            style={{
              backgroundColor: "var(--nb-tint-blue-bg)",
              color: "var(--nb-tint-blue-ink)",
            }}
          >
            {citations.length} 条引用
          </span>
          {verification ? (
            <span
              className="nb-pill"
              style={
                verification.unsupported_claims.length === 0
                  ? {
                      backgroundColor: "var(--nb-tint-green-bg)",
                      color: "var(--nb-tint-green-ink)",
                    }
                  : {
                      backgroundColor: "var(--nb-tint-amber-bg)",
                      color: "var(--nb-tint-amber-ink)",
                    }
              }
            >
              忠实度 {Math.round(verification.faithfulness_score * 100)}%
              {verification.unsupported_claims.length > 0
                ? ` · ${verification.unsupported_claims.length} 处待复核`
                : " · 已验真"}
            </span>
          ) : null}
        </div>

        <button
          type="button"
          className="nb-ghost-btn"
          aria-expanded={expanded}
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? "收起明细" : "展开得分与原文"}
        </button>
      </div>

      {expanded ? (
        <ul
          style={{
            listStyle: "none",
            margin: "var(--space-12) 0 0",
            padding: 0,
            display: "flex",
            flexDirection: "column",
            gap: "var(--space-8)",
          }}
        >
          {citations.map((c) => {
            const bd = c.score_breakdown;
            const isSelected = activeParaId === c.para_id;
            const scorePct = Math.round(((c.score ?? 0) * 100));
            const ftsPct = bd ? Math.min(100, Math.round((bd.fts / maxFts) * 100)) : 0;
            const vecPct = bd ? Math.min(100, Math.round(bd.vector * 100)) : 0;

            return (
              <li
                key={c.para_id}
                onClick={() => {
                  setActiveParaId((prev) => (prev === c.para_id ? null : c.para_id));
                  onSelectCitation?.(c);
                }}
                style={{
                  padding: "var(--space-12)",
                  borderRadius: "var(--nb-radius-sm, 8px)",
                  backgroundColor: isSelected ? "var(--nb-bg-hover)" : "var(--nb-bg)",
                  border: `var(--border-width, 1px) solid ${
                    isSelected ? "var(--nb-accent)" : "var(--nb-border)"
                  }`,
                  cursor: "pointer",
                  transition: "border-color var(--duration-fast) var(--ease-out)",
                }}
              >
                <div
                  className="flex items-center justify-between"
                  style={{ gap: "var(--space-8)" }}
                >
                  <span
                    style={{
                      fontSize: "var(--text-meta-size, 12px)",
                      fontWeight: 500,
                      color: "var(--nb-text)",
                    }}
                  >
                    {c.source_file}
                    {c.heading_path ? ` · ${c.heading_path}` : ""}
                    <span
                      style={{
                        marginLeft: 6,
                        color: "var(--nb-text-tertiary)",
                        fontFamily: "monospace",
                      }}
                    >
                      {c.para_id}
                    </span>
                  </span>
                  <span
                    style={{
                      fontSize: "var(--text-meta-size, 12px)",
                      fontWeight: 500,
                      color: "var(--nb-accent)",
                      fontFamily: "monospace",
                      whiteSpace: "nowrap",
                    }}
                  >
                    相关度 {scorePct}%
                  </span>
                </div>

                <p
                  style={{
                    margin: "6px 0 0",
                    fontSize: "var(--text-body-size, 14px)",
                    lineHeight: 1.55,
                    color: "var(--nb-text-secondary)",
                    display: isSelected ? "block" : "-webkit-box",
                    WebkitLineClamp: isSelected ? undefined : 2,
                    WebkitBoxOrient: "vertical",
                    overflow: "hidden",
                  }}
                >
                  {c.snippet || c.text}
                </p>

                {bd ? (
                  <div
                    className="flex flex-wrap items-center"
                    style={{
                      gap: "var(--space-12)",
                      marginTop: "var(--space-8)",
                      fontSize: 11,
                      color: "var(--nb-text-tertiary)",
                      fontFamily: "monospace",
                    }}
                  >
                    <span className="flex items-center" style={{ gap: 6 }}>
                      FTS5 {bd.fts.toFixed(2)}
                      <span className="nb-xray-track">
                        <span
                          className="nb-xray-fill"
                          style={{
                            width: `${ftsPct}%`,
                            backgroundColor: "var(--nb-accent)",
                          }}
                        />
                      </span>
                    </span>
                    <span className="flex items-center" style={{ gap: 6 }}>
                      Vec {bd.vector.toFixed(2)}
                      <span className="nb-xray-track">
                        <span
                          className="nb-xray-fill"
                          style={{
                            width: `${vecPct}%`,
                            backgroundColor: "var(--nb-tint-teal-ink)",
                          }}
                        />
                      </span>
                    </span>
                    <span>RRF {bd.rrf.toFixed(4)}</span>
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : null}
    </section>
  );
};
