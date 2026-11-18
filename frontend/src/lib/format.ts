/**
 * 展示格式化工具（DESIGN.md §8：元信息格式统一为「12 个来源 · 2024年4月21日」）。
 */

/** RFC 3339 UTC → 「2024年4月21日」 */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return `${d.getUTCFullYear()}年${d.getUTCMonth() + 1}月${d.getUTCDate()}日`;
}

/** RFC 3339 UTC → 「14:32」（UTC 时区，表格式对齐） */
export function formatTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const hh = String(d.getUTCHours()).padStart(2, "0");
  const mm = String(d.getUTCMinutes()).padStart(2, "0");
  return `${hh}:${mm}`;
}

/** 0.0-1.0 → 「45%」 */
export function formatPercent(v: number): string {
  return `${Math.round(v * 100)}%`;
}
