/**
 * 文档上传区单元测试（Step 2）：仅接受 .md / .docx / .doc，其余给出完整句子提示。
 */
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DocUploader } from "./DocUploader";

describe("DocUploader 文档上传", () => {
  it("接受 .md 文件并调用 onUpload", async () => {
    const user = userEvent.setup();
    const onUpload = vi.fn(async (_file: File) => {});
    render(<DocUploader onUpload={onUpload} />);

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, new File(["# 标题"], "note.md", { type: "text/markdown" }));

    expect(onUpload).toHaveBeenCalledTimes(1);
    expect(onUpload.mock.calls[0]?.[0]?.name).toBe("note.md");
  });

  it("拒绝 .txt 并给出完整句子提示", async () => {
    const user = userEvent.setup();
    const onUpload = vi.fn(async () => {});
    render(<DocUploader onUpload={onUpload} />);

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, new File(["x"], "note.txt", { type: "text/plain" }));

    expect(onUpload).not.toHaveBeenCalled();
    expect(await screen.findByText(/文件 note\.txt 无法入库：仅支持 \.md \/ \.docx \/ \.doc 文档/)).toBeInTheDocument();
  });

  it("拒绝 .pdf 与 .xlsx", async () => {
    const user = userEvent.setup();
    const onUpload = vi.fn(async () => {});
    render(<DocUploader onUpload={onUpload} />);

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, new File(["x"], "data.pdf", { type: "application/pdf" }));
    expect(onUpload).not.toHaveBeenCalled();
    expect(await screen.findByText(/文件 data\.pdf 无法入库/)).toBeInTheDocument();

    await user.upload(input, new File(["x"], "data.xlsx", { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }));
    expect(onUpload).not.toHaveBeenCalled();
    expect(screen.getAllByRole("alert").length).toBeGreaterThan(0);
  });

  it("disabled 时不允许点击选择文件", () => {
    render(<DocUploader onUpload={vi.fn()} disabled />);
    const trigger = screen.getByText("拖拽文档到此处，或点击选择文件").closest("button")!;
    expect(trigger).toBeDisabled();
  });

  it("拖拽悬停时整行填充 hover 色", () => {
    render(<DocUploader onUpload={vi.fn()} />);
    const trigger = screen.getByText("拖拽文档到此处，或点击选择文件").closest("button")!;
    fireEvent.dragOver(trigger);
    expect(trigger.style.backgroundColor).toBe("var(--nb-bg-hover)");
    fireEvent.dragLeave(trigger);
    expect(trigger.style.backgroundColor).toBe("var(--nb-bg-subtle)");
  });

  it("拖入合法文件直接入库，拖入非法文件给出提示", () => {
    const onUpload = vi.fn(async () => {});
    render(<DocUploader onUpload={onUpload} />);
    const trigger = screen.getByText("拖拽文档到此处，或点击选择文件").closest("button")!;

    const okFile = new File(["# x"], "ok.md", { type: "text/markdown" });
    fireEvent.drop(trigger, { dataTransfer: { files: [okFile] } });
    expect(onUpload).toHaveBeenCalledTimes(1);

    const badFile = new File(["x"], "bad.txt", { type: "text/plain" });
    fireEvent.drop(trigger, { dataTransfer: { files: [badFile] } });
    expect(onUpload).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/文件 bad\.txt 无法入库/)).toBeInTheDocument();
  });

  it("点击上传区打开文件选择器", () => {
    render(<DocUploader onUpload={vi.fn()} />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const clickSpy = vi.spyOn(input, "click");
    fireEvent.click(screen.getByText("拖拽文档到此处，或点击选择文件"));
    expect(clickSpy).toHaveBeenCalledTimes(1);
  });
});
