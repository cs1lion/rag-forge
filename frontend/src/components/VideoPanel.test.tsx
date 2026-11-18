/**
 * 视频工作室单元测试补充：播放器占位文案、队列概览与视频元素。
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { VideoPanel } from "./VideoPanel";
import type { VideoTask } from "../types";

const base = {
  qa_record_id: 1,
  created_at: "2026-11-18T10:00:00Z",
  started_at: null,
  finished_at: null,
  video_url: null,
  error: null,
  progress: 0,
};

function task(partial: Partial<VideoTask>): VideoTask {
  return { id: 1, ...base, ...partial } as VideoTask;
}

describe("VideoPanel 播放器占位文案", () => {
  it("running 态展示合成中占位", () => {
    render(<VideoPanel tasks={[task({ id: 1, status: "running", progress: 0.3, stage: "script" })]} runningCount={1} activeTaskId={1} />);
    expect(screen.getByText("视频正在合成，完成后即可在此播放。")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("queued 态展示排队占位", () => {
    render(<VideoPanel tasks={[task({ id: 1, status: "queued", queue_position: 2 })]} runningCount={0} activeTaskId={1} />);
    expect(screen.getByText("视频正在排队，前方任务合成完成后开始生成。")).toBeInTheDocument();
  });

  it("failed 态展示失败占位", () => {
    render(<VideoPanel tasks={[task({ id: 1, status: "failed", error: "x" })]} runningCount={0} activeTaskId={1} />);
    expect(screen.getByText("本次视频合成失败，可重新提问生成新任务。")).toBeInTheDocument();
  });

  it("无当前任务时展示引导占位", () => {
    render(<VideoPanel tasks={[]} runningCount={0} activeTaskId={null} />);
    expect(screen.getByText("提问后系统将自动生成问答视频。")).toBeInTheDocument();
  });

  it("done 态渲染 video 元素并指向 /api/videos/{id}/file", () => {
    render(<VideoPanel tasks={[task({ id: 4, status: "done", progress: 1, video_url: "/api/videos/4/file" })]} runningCount={0} activeTaskId={4} />);
    const video = document.querySelector("video");
    expect(video).not.toBeNull();
    expect(video!.getAttribute("src")).toBe("/api/videos/4/file");
    expect(video!.getAttribute("controls")).not.toBeNull();
  });

  it("running 行展示阶段与进度文案", () => {
    render(<VideoPanel tasks={[task({ id: 2, status: "running", stage: "mux", progress: 0.9 })]} runningCount={1} activeTaskId={2} />);
    expect(screen.getByText("生成中 · 音画合成阶段 · 90%")).toBeInTheDocument();
  });

  it("queued 无位次时按前方 0 个任务兜底", () => {
    render(<VideoPanel tasks={[task({ id: 1, status: "queued" })]} runningCount={0} activeTaskId={null} />);
    expect(screen.getByText("排队中 · 前方还有 0 个任务")).toBeInTheDocument();
  });

  it("running 无阶段时省略阶段前缀", () => {
    render(<VideoPanel tasks={[task({ id: 1, status: "running", progress: 0.2 })]} runningCount={1} activeTaskId={1} />);
    expect(screen.getByText("生成中 · 20%")).toBeInTheDocument();
  });

  it("failed 无原因时展示「未知错误」兜底", () => {
    render(<VideoPanel tasks={[task({ id: 1, status: "failed" })]} runningCount={0} activeTaskId={null} />);
    expect(screen.getByText("失败 · 未知错误")).toBeInTheDocument();
  });

  it("非当前任务不显示「· 当前」标记，done 无 video_url 时不渲染链接", () => {
    render(<VideoPanel tasks={[task({ id: 1, status: "done", progress: 1 })]} runningCount={0} activeTaskId={99} />);
    expect(screen.getByText("视频任务 #1")).toBeInTheDocument();
    expect(screen.queryByText(/· 当前/)).not.toBeInTheDocument();
    expect(screen.queryByText("播放 / 下载视频")).not.toBeInTheDocument();
  });
});
