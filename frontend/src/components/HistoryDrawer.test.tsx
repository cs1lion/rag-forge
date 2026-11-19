/**
 * 历史问答弹层单元测试（会话 4）：右上角按钮弹出、点击回看、删除记录。
 */
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { HistoryDrawer } from "./HistoryDrawer";
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

describe("HistoryDrawer 历史问答弹层", () => {
  it("open=false 时不渲染", () => {
    render(<HistoryDrawer open={false} records={[rec()]} selectedId={null} onSelect={vi.fn()} onDelete={vi.fn()} onClose={vi.fn()} />);
    expect(screen.queryByText("历史问答")).not.toBeInTheDocument();
  });

  it("open=true 时渲染问题列表与计数", () => {
    render(<HistoryDrawer open records={[rec()]} selectedId={null} onSelect={vi.fn()} onDelete={vi.fn()} onClose={vi.fn()} />);
    expect(screen.getByText("历史问答")).toBeInTheDocument();
    expect(screen.getByText("众赢科技 2025 年研发投入占营收比重是多少？")).toBeInTheDocument();
    expect(screen.getByText("共 1 条记录")).toBeInTheDocument();
  });

  it("点击条目回调 onSelect 并携带 id", () => {
    const onSelect = vi.fn();
    render(<HistoryDrawer open records={[rec()]} selectedId={null} onSelect={onSelect} onDelete={vi.fn()} onClose={vi.fn()} />);
    fireEvent.click(screen.getByText("众赢科技 2025 年研发投入占营收比重是多少？"));
    expect(onSelect).toHaveBeenCalledWith(1);
  });

  it("选中行带 aria-current 与高亮底色", () => {
    render(<HistoryDrawer open records={[rec()]} selectedId={1} onSelect={vi.fn()} onDelete={vi.fn()} onClose={vi.fn()} />);
    const btn = screen.getByText("众赢科技 2025 年研发投入占营收比重是多少？").closest("button")!;
    expect(btn).toHaveAttribute("aria-current", "true");
    expect(btn.closest("li")!.style.backgroundColor).toBe("var(--nb-bg-hover)");
  });

  it("点击删除按钮回调 onDelete 并携带 id", () => {
    const onDelete = vi.fn();
    render(<HistoryDrawer open records={[rec()]} selectedId={null} onSelect={vi.fn()} onDelete={onDelete} onClose={vi.fn()} />);
    fireEvent.click(screen.getByLabelText("删除历史问答 1"));
    expect(onDelete).toHaveBeenCalledWith(1);
  });

  it("点击遮罩或关闭按钮触发 onClose", () => {
    const onClose = vi.fn();
    render(<HistoryDrawer open records={[rec()]} selectedId={null} onSelect={vi.fn()} onDelete={vi.fn()} onClose={onClose} />);
    fireEvent.click(screen.getByLabelText("关闭历史问答"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("skipped 记录展示未生成视频的中性状态", () => {
    render(<HistoryDrawer open records={[rec({ video_status: "skipped" })]} selectedId={null} onSelect={vi.fn()} onDelete={vi.fn()} onClose={vi.fn()} />);
    expect(screen.getByText(/未生成视频/)).toBeInTheDocument();
    expect(screen.queryByText(/视频生成失败/)).not.toBeInTheDocument();
  });

  it("空列表给出完整句子空状态", () => {
    render(<HistoryDrawer open records={[]} selectedId={null} onSelect={vi.fn()} onDelete={vi.fn()} onClose={vi.fn()} />);
    expect(screen.getByText("还没有问答记录，提出第一个问题后会自动保存在这里。")).toBeInTheDocument();
  });
});
