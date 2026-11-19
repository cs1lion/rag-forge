/**
 * 已入库文档列表单元测试：勾选生效范围、全选、风险徽标、删除回调与悬停填充。
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

const props = {
  onToggleDoc: vi.fn(),
  onToggleAll: vi.fn(),
  onDelete: vi.fn(async () => {}),
};

describe("DocList 文档列表", () => {
  it("空列表给出完整句子空状态", () => {
    render(<DocList documents={[]} selectedIds={[]} {...props} />);
    expect(screen.getByText("知识库暂无文档，上传 .md / .docx / .doc 文件后即可提问。")).toBeInTheDocument();
    expect(screen.getByLabelText("全选文档")).toBeDisabled();
  });

  it("渲染文档标题与字数统计", () => {
    render(<DocList documents={[doc()]} selectedIds={["doc01"]} {...props} />);
    expect(screen.getByText("西海市众赢科技有限公司介绍")).toBeInTheDocument();
    expect(screen.getByText("8766 字")).toBeInTheDocument();
  });

  it("injection_flag=1 展示「含风险」徽标（自动识别），0 则不展示", () => {
    const { rerender } = render(<DocList documents={[doc({ injection_flag: 1 })]} selectedIds={["doc01"]} {...props} />);
    expect(screen.getByText("含风险")).toBeInTheDocument();
    expect(screen.getByText("含风险").getAttribute("title")).toContain("自动识别");
    rerender(<DocList documents={[doc()]} selectedIds={["doc01"]} {...props} />);
    expect(screen.queryByText("含风险")).not.toBeInTheDocument();
  });

  it("勾选框反映选中状态，点击回调 doc_id", () => {
    const onToggleDoc = vi.fn();
    render(<DocList documents={[doc()]} selectedIds={[]} {...props} onToggleDoc={onToggleDoc} />);
    const cb = screen.getByLabelText("选择文档 西海市众赢科技有限公司介绍") as HTMLInputElement;
    expect(cb.checked).toBe(false);
    fireEvent.click(cb);
    expect(onToggleDoc).toHaveBeenCalledWith("doc01");
  });

  it("全选：全部选中时勾选，部分选中时未勾选；点击回调 onToggleAll", () => {
    const onToggleAll = vi.fn();
    const { rerender } = render(
      <DocList documents={[doc(), doc({ doc_id: "doc02", title: "第二篇" })]} selectedIds={["doc01", "doc02"]} {...props} onToggleAll={onToggleAll} />,
    );
    const all = screen.getByLabelText("全选文档") as HTMLInputElement;
    expect(all.checked).toBe(true);
    expect(screen.getByText("全选 · 已选 2 / 2 篇生效")).toBeInTheDocument();
    fireEvent.click(all);
    expect(onToggleAll).toHaveBeenCalledTimes(1);

    rerender(
      <DocList documents={[doc(), doc({ doc_id: "doc02", title: "第二篇" })]} selectedIds={["doc02"]} {...props} onToggleAll={onToggleAll} />,
    );
    expect((screen.getByLabelText("全选文档") as HTMLInputElement).checked).toBe(false);
    expect(screen.getByText("全选 · 已选 1 / 2 篇生效")).toBeInTheDocument();
  });

  it("点击删除按钮回调 doc_id，busy 时禁用", async () => {
    const onDelete = vi.fn(async () => {});
    render(<DocList documents={[doc()]} selectedIds={["doc01"]} {...props} onDelete={onDelete} busy />);
    const btn = screen.getByLabelText("删除文档 西海市众赢科技有限公司介绍");
    expect(btn).toBeDisabled();
    fireEvent.click(btn);
    expect(onDelete).not.toHaveBeenCalled();
  });

  it("行悬停整行填充 --nb-bg-hover", () => {
    render(<DocList documents={[doc()]} selectedIds={["doc01"]} {...props} />);
    const row = screen.getByText("西海市众赢科技有限公司介绍").closest("li")!;
    fireEvent.mouseEnter(row);
    expect(row.style.backgroundColor).toBe("var(--nb-bg-hover)");
    fireEvent.mouseLeave(row);
    expect(row.style.backgroundColor).toBe("transparent");
  });

  it("删除按钮悬停白底、非 busy 时点击回调", () => {
    const onDelete = vi.fn(async () => {});
    render(<DocList documents={[doc()]} selectedIds={["doc01"]} {...props} onDelete={onDelete} />);
    const btn = screen.getByLabelText("删除文档 西海市众赢科技有限公司介绍");
    fireEvent.mouseEnter(btn);
    expect(btn.style.backgroundColor).toBe("var(--nb-bg)");
    fireEvent.mouseLeave(btn);
    expect(btn.style.backgroundColor).toBe("transparent");
    fireEvent.click(btn);
    expect(onDelete).toHaveBeenCalledWith("doc01");
  });
});
