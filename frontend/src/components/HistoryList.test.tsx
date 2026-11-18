/**
 * 历史问答列表单元测试（Step 2）：点击回看、选中态、视频状态徽标（文字 + 图标）。
 */
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { HistoryList } from "./HistoryList";
import type { QaRecordSummary } from "../types";

const rec = (over: Partial<QaRecordSummary> = {}): QaRecordSummary => ({
  id: 1,
  question: "众赢科技 2025 年研发投入占营收比重是多少？",
  answer_summary: "超过 75%。",
  video_task_id: 3,
  video_status: "done",
  created_at: "2026-11-18T10:00:00Z",
  ...over,
});

describe("HistoryList 历史问答", () => {
  it("空列表给出完整句子空状态", () => {
    render(<HistoryList records={[]} selectedId={null} onSelect={vi.fn()} />);
    expect(screen.getByText("还没有问答记录，提出第一个问题后会自动保存在这里。")).toBeInTheDocument();
  });

  it("渲染问题文本与「日期 · 时间」元信息", () => {
    render(<HistoryList records={[rec()]} selectedId={null} onSelect={vi.fn()} />);
    expect(screen.getByText("众赢科技 2025 年研发投入占营收比重是多少？")).toBeInTheDocument();
    expect(screen.getByText("2026年11月18日 10:00")).toBeInTheDocument();
  });

  it("四种视频状态均展示文字徽标（不只靠颜色）", () => {
    const { rerender } = render(<HistoryList records={[rec({ video_status: "queued" })]} selectedId={null} onSelect={vi.fn()} />);
    expect(screen.getByText("排队中")).toBeInTheDocument();
    rerender(<HistoryList records={[rec({ video_status: "running" })]} selectedId={null} onSelect={vi.fn()} />);
    expect(screen.getByText("生成中")).toBeInTheDocument();
    rerender(<HistoryList records={[rec({ video_status: "done" })]} selectedId={null} onSelect={vi.fn()} />);
    expect(screen.getByText("可播放")).toBeInTheDocument();
    rerender(<HistoryList records={[rec({ video_status: "failed" })]} selectedId={null} onSelect={vi.fn()} />);
    expect(screen.getByText("失败")).toBeInTheDocument();
  });

  it("video_status 为 null 时不渲染状态徽标", () => {
    render(<HistoryList records={[rec({ video_status: null, video_task_id: null })]} selectedId={null} onSelect={vi.fn()} />);
    expect(screen.queryByText("可播放")).not.toBeInTheDocument();
  });

  it("点击条目回调 id，选中行填充 hover 色并带 aria-current", () => {
    const onSelect = vi.fn(async () => {});
    render(<HistoryList records={[rec()]} selectedId={1} onSelect={onSelect} />);
    const btn = screen.getByRole("button", { name: /众赢科技/ });
    expect(btn).toHaveAttribute("aria-current", "true");
    expect(btn.style.backgroundColor).toBe("var(--nb-bg-hover)");
    fireEvent.click(btn);
    expect(onSelect).toHaveBeenCalledWith(1);
  });
});
