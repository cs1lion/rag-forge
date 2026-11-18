/**
 * 引用来源卡片单元测试（Step 3）：横向 Sources 条 + 点击展开四维溯源
 * （doc_id / source_file / heading_path / para_id + 原文段落 + 相似度）。
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SourcesBar } from "./SourcesBar";
import type { Citation } from "../types";

const citation: Citation = {
  doc_id: "doc05",
  doc_title: "西海市众赢科技有限公司介绍",
  source_file: "西海市众赢科技有限公司介绍.docx",
  heading_path: "西海市众赢科技有限公司介绍 > 五、研发体系与投入",
  para_id: "doc05#p041",
  snippet: "2025 年，公司研发投入 11 亿元，研发投入占营业收入的比重超过 75%。",
  score: 0.87,
};

describe("SourcesBar 引用卡片", () => {
  it("无引用时不渲染任何内容", () => {
    const { container } = render(<SourcesBar citations={[]} />);
    expect(container.innerHTML).toBe("");
  });

  it("默认展示来源计数与文档名、章节路径摘要", () => {
    render(<SourcesBar citations={[citation]} createdAt="2026-11-18T10:00:00Z" />);
    expect(screen.getByText("1 个来源 · 2026年11月18日")).toBeInTheDocument();
    expect(screen.getByText(citation.source_file)).toBeInTheDocument();
    expect(screen.getByText(citation.heading_path)).toBeInTheDocument();
    // 未展开前不展示原文段落
    expect(screen.queryByText(citation.snippet)).not.toBeInTheDocument();
  });

  it("点击卡片展开四维溯源与原文段落，再次点击收起", async () => {
    const user = userEvent.setup();
    render(<SourcesBar citations={[citation]} />);

    const card = screen.getByRole("option");
    expect(card).toHaveAttribute("aria-selected", "false");
    await user.click(card);

    expect(card).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("原文文件：西海市众赢科技有限公司介绍.docx")).toBeInTheDocument();
    expect(screen.getByText("语料编号：doc05")).toBeInTheDocument();
    expect(screen.getByText("章节路径：西海市众赢科技有限公司介绍 > 五、研发体系与投入")).toBeInTheDocument();
    expect(screen.getByText("段落定位：doc05#p041")).toBeInTheDocument();
    expect(screen.getByText(citation.snippet)).toBeInTheDocument();
    expect(screen.getByText("相似度 87%")).toBeInTheDocument();

    await user.click(card);
    expect(screen.queryByText("段落定位：doc05#p041")).not.toBeInTheDocument();
  });

  it("多引用时各卡片独立展开", async () => {
    const user = userEvent.setup();
    const second: Citation = { ...citation, para_id: "doc06#p002", doc_id: "doc06", source_file: "澎湃教育.docx", heading_path: "澎湃 > 一、概览", score: 0.72 };
    render(<SourcesBar citations={[citation, second]} />);

    const cards = screen.getAllByRole("option");
    await user.click(cards[1]);
    expect(screen.getByText("段落定位：doc06#p002")).toBeInTheDocument();
    expect(screen.queryByText("段落定位：doc05#p041")).not.toBeInTheDocument();
  });
});
