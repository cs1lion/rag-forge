/**
 * 左侧栏单元测试（Step 2）：文档库 + 历史问答组合与上传禁用态。
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { Sidebar } from "./Sidebar";
import type { DocumentRecord, QaRecordSummary } from "../types";

const doc: DocumentRecord = {
  doc_id: "doc01",
  title: "众赢科技介绍",
  source_file: "众赢.docx",
  source_format: "docx",
  parse_method: "OOXML",
  char_count: 100,
  injection_flag: 0,
  chunk_count: 2,
  created_at: "2026-11-18T10:00:00Z",
};

const rec: QaRecordSummary = {
  id: 1,
  question: "q?",
  answer_summary: "a",
  video_task_id: 3,
  video_status: "done",
  created_at: "2026-11-18T10:00:00Z",
};

describe("Sidebar 左侧栏", () => {
  it("渲染文档库与历史问答两个面板及计数", () => {
    render(
      <Sidebar
        documents={[doc]}
        qaRecords={[rec]}
        selectedHistoryId={null}
        onUpload={vi.fn()}
        onDeleteDoc={vi.fn()}
        onSelectHistory={vi.fn()}
        uploading={false}
      />,
    );
    expect(screen.getByText("文档库")).toBeInTheDocument();
    expect(screen.getByText("1 篇")).toBeInTheDocument();
    expect(screen.getByText("历史问答")).toBeInTheDocument();
    expect(screen.getByText("1 条")).toBeInTheDocument();
    expect(screen.getByText("众赢科技介绍")).toBeInTheDocument();
    expect(screen.getByText("q?")).toBeInTheDocument();
  });

  it("uploading 时上传区禁用", () => {
    render(
      <Sidebar
        documents={[]}
        qaRecords={[]}
        selectedHistoryId={null}
        onUpload={vi.fn()}
        onDeleteDoc={vi.fn()}
        onSelectHistory={vi.fn()}
        uploading
      />,
    );
    expect(screen.getByText("拖拽文档到此处，或点击选择文件").closest("button")).toBeDisabled();
  });
});
