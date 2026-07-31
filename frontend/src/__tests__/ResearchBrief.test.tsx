import { describe, it, expect, vi } from "vitest"
import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { ResearchBrief } from "@/components/ResearchBrief"
import type { ResearchBrief as ResearchBriefType } from "@/hooks/useResearch"

const brief: ResearchBriefType = {
  id: "b1",
  matter_id: "m1",
  query: "negligence liability",
  created_at: "2025-01-15T10:30:00Z",
  summary: "This matter concerns a potential negligence claim against the defendant.",
  sections: [
    {
      title: "Key Precedents",
      content:
        "The court in **Smith v. Jones** held that a duty of care exists. [1] Further analysis supports liability. [2]",
      citations: [
        {
          citation: "Smith v. Jones, 123 F.3d 456 (2d Cir. 2001)",
          passage:
            "We hold that a landowner owes a duty of care to invited guests, and this duty extends to foreseeable third parties on the premises.",
          relevance_score: 0.92,
          corpus_document_id: "d1",
        },
        {
          citation: "Doe v. Roe, 789 F. Supp. 2d 321 (D. Mass. 2012)",
          passage:
            "Under the Restatement (Second) of Torts, liability attaches when the harm is within the scope of the foreseeable risk created by the defendant's conduct.",
          relevance_score: 0.45,
          corpus_document_id: "d2",
        },
      ],
    },
    {
      title: "Applicable Statutes",
      content: "Relevant statutes include the state tort reform act.",
      citations: [],
    },
  ],
  status: "complete",
}

const longPassage =
  "Lorem ipsum dolor sit amet, consectetur adipiscing elit. ".repeat(40)

function longPassageBrief(): ResearchBriefType {
  return {
    ...brief,
    sections: [
      {
        title: "Key Precedents",
        content: "The court held that a duty exists. [1]",
        citations: [
          {
            citation: "Smith v. Jones, 123 F.3d 456",
            passage: longPassage,
            relevance_score: 0.8,
            corpus_document_id: "d1",
          },
        ],
      },
    ],
  }
}

function renderBrief(
  props: Partial<React.ComponentProps<typeof ResearchBrief>> = {}
) {
  return render(
    <ResearchBrief
      matterId="m1"
      brief={null}
      status="not_generated"
      loading={false}
      error={null}
      onRegenerate={vi.fn()}
      {...props}
    />
  )
}

describe("ResearchBrief status states", () => {
  it("renders the not_generated state", () => {
    renderBrief({ status: "not_generated" })
    expect(screen.getByTestId("brief-not-generated")).toHaveTextContent(
      "No brief generated yet"
    )
  })

  it("renders the generating state with a spinner", () => {
    renderBrief({ status: "generating", loading: true })
    expect(screen.getByTestId("brief-generating")).toHaveTextContent(
      "Analyzing passages..."
    )
  })

  it("renders the no_results state", () => {
    renderBrief({ status: "no_results" })
    expect(screen.getByTestId("brief-no-results")).toHaveTextContent(
      "No relevant precedents found"
    )
  })

  it("renders the error state with the error message", () => {
    renderBrief({ status: "error", error: "Brief API unavailable" })
    expect(screen.getByTestId("brief-error")).toHaveTextContent(
      "Brief generation failed"
    )
    expect(screen.getByRole("alert")).toHaveTextContent("Brief API unavailable")
  })
})

describe("ResearchBrief brief display", () => {
  it("renders a complete brief with summary, sections, and citations", () => {
    renderBrief({ brief, status: "complete" })
    expect(screen.getByTestId("brief-complete")).toBeInTheDocument()

    expect(screen.getByText("Research Brief")).toBeInTheDocument()
    expect(screen.getByText("negligence liability")).toBeInTheDocument()
    expect(screen.getByText("Summary")).toBeInTheDocument()
    expect(
      screen.getByText("This matter concerns a potential negligence claim against the defendant.")
    ).toBeInTheDocument()

    expect(screen.getByText("Key Precedents")).toBeInTheDocument()
    expect(screen.getByText("Applicable Statutes")).toBeInTheDocument()

    // Bold inline formatting in the content.
    expect(screen.getByText("Smith v. Jones")).toBeInTheDocument()

    // References list.
    expect(
      screen.getByText("Smith v. Jones, 123 F.3d 456 (2d Cir. 2001)")
    ).toBeInTheDocument()
    expect(
      screen.getByText("Doe v. Roe, 789 F. Supp. 2d 321 (D. Mass. 2012)")
    ).toBeInTheDocument()
  })

  it("shows a warning banner for a partial brief", () => {
    renderBrief({ brief, status: "partial" })
    expect(screen.getByTestId("brief-partial-warning")).toHaveTextContent(
      "Some sections could not be completed"
    )
    expect(screen.getByText("Partial")).toBeInTheDocument()
  })

  it("expands an inline citation card when a reference is clicked", async () => {
    const user = userEvent.setup()
    renderBrief({ brief, status: "complete" })

    expect(screen.queryByTestId("citation-card")).not.toBeInTheDocument()

    await user.click(screen.getByTitle("Citation 1"))
    const citationCard = screen.getByTestId("citation-card")
    expect(
      within(citationCard).getByText("Smith v. Jones, 123 F.3d 456 (2d Cir. 2001)")
    ).toBeInTheDocument()
    expect(
      within(citationCard).getByText(/We hold that a landowner owes a duty of care/)
    ).toBeInTheDocument()
    expect(
      within(citationCard).getByRole("link", { name: /view source/i })
    ).toHaveAttribute("href", "/matters/m1")
    expect(
      within(citationCard).getByLabelText("Relevance score 92%")
    ).toBeInTheDocument()

    // Clicking again collapses it.
    await user.click(screen.getByTitle("Citation 1"))
    expect(screen.queryByTestId("citation-card")).not.toBeInTheDocument()
  })

  it("collapses and expands sections independently", async () => {
    const user = userEvent.setup()
    renderBrief({ brief, status: "complete" })

    const collapseButtons = screen.getAllByRole("button", { name: /collapse/i })
    expect(collapseButtons).toHaveLength(2)

    // Collapse the first section.
    await user.click(collapseButtons[0])
    expect(collapseButtons[0]).toHaveAttribute("aria-expanded", "false")
    // Its inline citations are no longer rendered...
    expect(screen.queryByTitle("Citation 1")).not.toBeInTheDocument()
    // ...but the second section is still visible.
    expect(
      screen.getByText("Relevant statutes include the state tort reform act.")
    ).toBeInTheDocument()

    // Re-expand it.
    await user.click(screen.getByRole("button", { name: /expand/i }))
    expect(screen.getByTitle("Citation 1")).toBeInTheDocument()
  })
})

describe("ResearchBrief actions", () => {
  it("opens a confirmation dialog and calls onRegenerate on confirm", async () => {
    const onRegenerate = vi.fn()
    const user = userEvent.setup()
    renderBrief({ brief, status: "complete", onRegenerate })

    await user.click(screen.getByRole("button", { name: /^regenerate$/i }))

    const dialog = screen.getByRole("dialog")
    expect(dialog).toHaveTextContent("Regenerate brief?")
    expect(dialog).toHaveTextContent("This will replace the current brief.")

    await user.click(within(dialog).getByRole("button", { name: /regenerate/i }))
    expect(onRegenerate).toHaveBeenCalledWith("negligence liability")
  })

  it("does not call onRegenerate when cancelled", async () => {
    const onRegenerate = vi.fn()
    const user = userEvent.setup()
    renderBrief({ brief, status: "complete", onRegenerate })

    await user.click(screen.getByRole("button", { name: /^regenerate$/i }))
    await user.click(
      within(screen.getByRole("dialog")).getByRole("button", {
        name: /cancel/i,
      })
    )

    expect(onRegenerate).not.toHaveBeenCalled()
  })

  it("copies the brief to the clipboard", async () => {
    // NOTE: userEvent.setup() stubs navigator.clipboard, so install our own
    // mock afterwards.
    const user = userEvent.setup()
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    })
    renderBrief({ brief, status: "complete" })

    await user.click(screen.getByRole("button", { name: /copy brief/i }))

    expect(writeText).toHaveBeenCalledTimes(1)
    const text = writeText.mock.calls[0][0] as string
    expect(text).toContain("Research Brief: negligence liability")
    expect(text).toContain("This matter concerns a potential negligence claim")
    expect(text).toContain("Key Precedents")
    expect(text).toContain("Smith v. Jones, 123 F.3d 456 (2d Cir. 2001)")
  })

  it("truncates long citation passages with a show more toggle", async () => {
    const user = userEvent.setup()
    renderBrief({ brief: longPassageBrief(), status: "complete" })

    await user.click(screen.getByTitle("Citation 1"))

    expect(screen.getByRole("button", { name: /show more/i })).toBeInTheDocument()
    const citationCard = screen.getByTestId("citation-card")
    const passage = within(citationCard).getByText(/Lorem ipsum/)
    // Truncated passage ends with "..."
    expect(passage.textContent).toMatch(/\.\.\.$/)

    await user.click(screen.getByRole("button", { name: /show more/i }))
    expect(screen.getByRole("button", { name: /show less/i })).toBeInTheDocument()
    expect(passage.textContent).toContain("Lorem ipsum dolor sit amet")
    expect(passage.textContent).not.toMatch(/\.\.\.$/)
  })
})
