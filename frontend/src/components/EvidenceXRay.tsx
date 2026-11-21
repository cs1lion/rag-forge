import React from "react";
import type { EvidenceCitation, VerificationReport } from "../hooks/useQaStream";

interface EvidenceXRayProps {
  citations: EvidenceCitation[];
  verification?: VerificationReport | null;
  onSelectCitation?: (citation: EvidenceCitation) => void;
}

/**
 * P3 可解释性工作台组件：可视化展示每条引用的 FTS5 词法分、向量语义分、RRF 融合分，
 * 以及 P2 声明级忠实度校验结果。
 */
export const EvidenceXRay: React.FC<EvidenceXRayProps> = ({
  citations,
  verification,
  onSelectCitation,
}) => {
  if (!citations.length) {
    return null;
  }

  return (
    <aside className="border-t border-slate-200 pt-4 mt-4 space-y-3" aria-label="检索证据透视">
      <div className="flex items-center justify-between text-xs text-slate-600">
        <span className="font-semibold text-slate-900">
          检索证据透视（{citations.length} 条命中）
        </span>
        {verification && (
          <span
            className={
              verification.unsupported_claims.length === 0
                ? "font-mono text-emerald-700"
                : "font-mono text-amber-700"
            }
          >
            忠实度 {Math.round(verification.faithfulness_score * 100)}%
            {verification.unsupported_claims.length > 0
              ? ` · ${verification.unsupported_claims.length} 处待复核`
              : " · 已验真"}
          </span>
        )}
      </div>

      <ul className="space-y-2">
        {citations.map((c) => {
          const bd = c.score_breakdown;
          return (
            <li
              key={c.para_id}
              onClick={() => onSelectCitation?.(c)}
              className="border-b border-slate-100 pb-2 cursor-pointer hover:bg-slate-50 transition-colors"
            >
              <div className="flex items-center justify-between text-xs">
                <span className="font-medium text-slate-900 truncate">
                  {c.source_file} · {c.heading_path || c.para_id}
                </span>
                <span className="font-mono text-blue-700 shrink-0 ml-2">
                  {(c.score * 100).toFixed(0)}%
                </span>
              </div>
              <p className="text-xs text-slate-600 line-clamp-2 mt-1">
                {c.snippet || c.text}
              </p>
              {bd && (
                <div className="flex gap-3 mt-1 font-mono text-[11px] text-slate-500">
                  <span>FTS5: {bd.fts.toFixed(2)}</span>
                  <span>Vec: {bd.vector.toFixed(2)}</span>
                  <span>RRF: {bd.rrf.toFixed(4)}</span>
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </aside>
  );
};
