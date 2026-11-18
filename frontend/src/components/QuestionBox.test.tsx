/**
 * 提问入口单元测试（Step 3）：输入、回车/按钮提交、空输入与 disabled 拦截、示例胶囊。
 */
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QuestionBox } from "./QuestionBox";

describe("QuestionBox 提问入口", () => {
  it("输入后点击「提问」提交并清空输入框", async () => {
    const user = userEvent.setup();
    const onAsk = vi.fn();
    render(<QuestionBox onAsk={onAsk} disabled={false} examples={[]} />);
    await user.type(screen.getByLabelText("提问"), "研发投入是多少？");
    await user.click(screen.getByRole("button", { name: "提问" }));
    expect(onAsk).toHaveBeenCalledWith("研发投入是多少？");
    expect(screen.getByLabelText("提问")).toHaveValue("");
  });

  it("回车键同样提交", async () => {
    const user = userEvent.setup();
    const onAsk = vi.fn();
    render(<QuestionBox onAsk={onAsk} disabled={false} examples={[]} />);
    await user.type(screen.getByLabelText("提问"), "问题A{enter}");
    expect(onAsk).toHaveBeenCalledWith("问题A");
  });

  it("空输入与纯空白不提交、按钮禁用", () => {
    const onAsk = vi.fn();
    render(<QuestionBox onAsk={onAsk} disabled={false} examples={[]} />);
    const btn = screen.getByRole("button", { name: "提问" });
    expect(btn).toBeDisabled();
    fireEvent.click(btn);
    expect(onAsk).not.toHaveBeenCalled();
  });

  it("disabled 时输入框与示例按钮均禁用", () => {
    render(<QuestionBox onAsk={vi.fn()} disabled examples={["示例"]} />);
    expect(screen.getByLabelText("提问")).toBeDisabled();
    expect(screen.getByRole("button", { name: "示例" })).toBeDisabled();
  });

  it("示例问题以胶囊按钮渲染并可直接提交", async () => {
    const user = userEvent.setup();
    const onAsk = vi.fn();
    render(<QuestionBox onAsk={onAsk} disabled={false} examples={["众赢科技研发投入？"]} />);
    expect(screen.getByText("示例问题")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "众赢科技研发投入？" }));
    expect(onAsk).toHaveBeenCalledWith("众赢科技研发投入？");
  });

  it("无示例时不渲染示例区", () => {
    render(<QuestionBox onAsk={vi.fn()} disabled={false} examples={[]} />);
    expect(screen.queryByText("示例问题")).not.toBeInTheDocument();
  });

  it("提问按钮与示例胶囊悬停填充 hover 色", async () => {
    const user = userEvent.setup();
    render(<QuestionBox onAsk={vi.fn()} disabled={false} examples={["示例"]} />);
    await user.type(screen.getByLabelText("提问"), "问题");
    const submit = screen.getByRole("button", { name: "提问" });
    fireEvent.mouseEnter(submit);
    expect(submit.style.backgroundColor).toBe("var(--nb-bg-hover)");
    fireEvent.mouseLeave(submit);
    expect(submit.style.backgroundColor).toBe("var(--nb-bg)");
    const chip = screen.getByRole("button", { name: "示例" });
    fireEvent.mouseEnter(chip);
    expect(chip.style.backgroundColor).toBe("var(--nb-bg-hover)");
    fireEvent.mouseLeave(chip);
    expect(chip.style.backgroundColor).toBe("var(--nb-bg)");
  });
});
