import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { EvidenceXRay } from "./EvidenceXRay";

describe("EvidenceXRay", () => {
  const sampleCitations = [
    {
      doc_id: "doc01",
      source_file: "travel_policy.docx",
      heading_path: "差旅规范 > 住宿",
      para_id: "doc01#p001",
      snippet: "一线城市出差酒店报销上限为每晚 680 元。",
      score: 0.94,
      score_breakdown: { fts: 4.12, vector: 0.87, rrf: 0.0321 },
    },
  ];

  it("returns null when citations are empty", () => {
    const { container } = render(<EvidenceXRay citations={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders summary badge and expands score breakdown on click", () => {
    const onSelect = vi.fn();
    render(
      <EvidenceXRay
        citations={sampleCitations}
        verification={{
          faithfulness_score: 1.0,
          total_claims: 1,
          supported_claims: 1,
          unsupported_claims: [],
        }}
        onSelectCitation={onSelect}
      />
    );

    expect(screen.getByText("证据透视 X-Ray")).toBeTruthy();
    expect(screen.getByText(/忠实度 100%/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "展开得分与原文" }));
    expect(screen.getByText(/FTS5 4\.12/)).toBeTruthy();
    expect(screen.getByText(/Vec 0\.87/)).toBeTruthy();

    fireEvent.click(screen.getByText(/travel_policy\.docx/));
    expect(onSelect).toHaveBeenCalledTimes(1);
  });
});
