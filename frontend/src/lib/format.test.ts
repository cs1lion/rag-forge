/**
 * 展示格式化工具单元测试（DESIGN.md §8 元信息格式）。
 */
import { describe, expect, it } from "vitest";
import { formatDate, formatPercent, formatTime } from "./format";

describe("展示格式化", () => {
  it("formatDate 输出「2026年11月18日」", () => {
    expect(formatDate("2026-11-18T10:00:00Z")).toBe("2026年11月18日");
  });

  it("formatDate 对空值与非法日期返回空串", () => {
    expect(formatDate(null)).toBe("");
    expect(formatDate(undefined)).toBe("");
    expect(formatDate("not-a-date")).toBe("");
  });

  it("formatTime 输出 UTC 「HH:MM」补零格式", () => {
    expect(formatTime("2026-11-18T10:00:00Z")).toBe("10:00");
    expect(formatTime("2026-11-18T09:05:00Z")).toBe("09:05");
    expect(formatTime(null)).toBe("");
    expect(formatTime(undefined)).toBe("");
    expect(formatTime("not-a-date")).toBe("");
  });

  it("formatPercent 四舍五入 0-100", () => {
    expect(formatPercent(0)).toBe("0%");
    expect(formatPercent(0.456)).toBe("46%");
    expect(formatPercent(1)).toBe("100%");
  });
});
