/**
 * 左侧栏单元测试：文档库面板（勾选生效范围）与上传禁用态。
 * 历史问答列表已迁至顶栏「历史」按钮弹层（会话 4），侧栏不再承载。
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { Sidebar } from "./Sidebar";
import type { DocumentRecord } from "../types";

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

const baseProps = {
  onUpload: vi.fn(),
  onDeleteDoc: vi.fn(),
  onToggleDoc: vi.fn(),
  onToggleAllDocs: vi.fn(),
};

describe("Sidebar 左侧栏", () => {
  it("渲染文档库面板与计数，默认显示全选状态", () => {
    render(
      <Sidebar documents={[doc]} selectedDocIds={["doc01"]} {...baseProps} uploading={false} />,
    );
    expect(screen.getByText("文档库")).toBeInTheDocument();
    expect(screen.getByText("1 篇")).toBeInTheDocument();
    expect(screen.getByText("众赢科技介绍")).toBeInTheDocument();
    expect(screen.getByLabelText("全选文档")).toBeChecked();
  });

  it("uploading 时上传区禁用", () => {
    render(<Sidebar documents={[]} selectedDocIds={[]} {...baseProps} uploading />);
    expect(screen.getByText("拖拽文档到此处，或点击选择文件").closest("button")).toBeDisabled();
  });
});
