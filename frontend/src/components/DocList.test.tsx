/**
 * 已入库文档列表单元测试（Step 2）：截断、字数、注入隔离徽标、删除回调与悬停填充。
 */
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { DocList } from "./DocList";
import type { DocumentRecord } from "../types";

const doc = (over: Partial<DocumentRecord> = {}): DocumentRecord => ({
  doc_id: "doc01",
  title: "西海市众赢科技有限公司介绍",
  source_file: "西海市众赢科技有限公司介绍.docx",
  source_format: "docx",
  parse_method: "OOXML(word/document.xml) 解析",
  char_count: 8766,
  injection_flag: 0,
  chunk_count: 74,
  created_at: "2026-11-18T10:00:00Z",
  ...over,
});

describe("DocList 文档列表", () => {
  it("空列表给出完整句子空状态", () => {
    render(<DocList documents={[]} onDelete={vi.fn()} />);
    expect(screen.getByText("知识库暂无文档，上传 .md / .docx / .doc 文件后即可提问。")).toBeInTheDocument();
  });

  it("渲染文档标题与字数统计", () => {
    render(<DocList documents={[doc()]} onDelete={vi.fn()} />);
    expect(screen.getByText("西海市众赢科技有限公司介绍")).toBeInTheDocument();
    expect(screen.getByText("8766 字")).toBeInTheDocument();
  });

  it("injection_flag=1 展示「已隔离」徽标，0 则不展示", () => {
    render(<DocList documents={[doc({ injection_flag: 1 })]} onDelete={vi.fn()} />);
    expect(screen.getByText("已隔离")).toBeInTheDocument();
    expect(screen.getByText("已隔离").getAttribute("title")).toContain("越权指令");
  });

  it("点击删除按钮回调 doc_id，busy 时禁用", async () => {
    const onDelete = vi.fn(async () => {});
    render(<DocList documents={[doc()]} onDelete={onDelete} busy />);
    const btn = screen.getByLabelText("删除文档 西海市众赢科技有限公司介绍");
    expect(btn).toBeDisabled();
    fireEvent.click(btn);
    expect(onDelete).not.toHaveBeenCalled();
  });

  it("行悬停整行填充 --nb-bg-hover", () => {
    render(<DocList documents={[doc()]} onDelete={vi.fn()} />);
    const row = screen.getByText("西海市众赢科技有限公司介绍").closest("li")!;
    fireEvent.mouseEnter(row);
    expect(row.style.backgroundColor).toBe("var(--nb-bg-hover)");
    fireEvent.mouseLeave(row);
    expect(row.style.backgroundColor).toBe("transparent");
  });

  it("删除按钮悬停白底、非 busy 时点击回调", () => {
    const onDelete = vi.fn(async () => {});
    render(<DocList documents={[doc()]} onDelete={onDelete} />);
    const btn = screen.getByLabelText("删除文档 西海市众赢科技有限公司介绍");
    fireEvent.mouseEnter(btn);
    expect(btn.style.backgroundColor).toBe("var(--nb-bg)");
    fireEvent.mouseLeave(btn);
    expect(btn.style.backgroundColor).toBe("transparent");
    fireEvent.click(btn);
    expect(onDelete).toHaveBeenCalledWith("doc01");
  });
});
