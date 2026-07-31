import { describe, it, expect, vi } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { ResearchSearch } from "@/components/ResearchSearch"
import { apiFetch } from "@/lib/api"
import type { SearchResultItem } from "@/hooks/useResearch"

vi.mock("@/lib/api", () => ({
  apiFetch: vi.fn(),
}))

const mockApiFetch = vi.mocked(apiFetch)

const results: SearchResultItem[] = [
  {
    chunk_id: "c1",
    corpus_document_id: "d1",
    text: "The defendant owed a duty of care to the plaintiff in this negligence action.",
    case_name: "Roe v. Wade",
    citation: "410 U.S. 113",
    court: "Supreme Court",
    year: 1973,
    relevance_score: 0.95,
  },
  {
    chunk_id: "c2",
    corpus_document_id: "d2",
    text: "Separate educational facilities are inherently unequal.",
    case_name: "Brown v. Board of Education",
    citation: "347 U.S. 483",
    court: "Supreme Court",
    year: 1954,
    relevance_score: 0.5,
  },
]

const searchResponse = {
  results,
  total_results: results.length,
  query_used: "negligence",
}

async function performSearch(user: ReturnType<typeof userEvent.setup>, query = "negligence") {
  await user.type(screen.getByLabelText("Search query"), query)
  await user.click(screen.getByRole("button", { name: /^search$/i }))
}

describe("ResearchSearch", () => {
  it("renders with the matterId prop and a search input", () => {
    render(<ResearchSearch matterId="m1" />)
    expect(screen.getByLabelText("Search query")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /^search$/i })).toBeInTheDocument()
  })

  it("updates the search input on typing", async () => {
    const user = userEvent.setup()
    render(<ResearchSearch matterId="m1" />)

    const input = screen.getByLabelText("Search query")
    await user.type(input, "breach of contract")
    expect(input).toHaveValue("breach of contract")
  })

  it("shows and hides the filter controls", async () => {
    const user = userEvent.setup()
    render(<ResearchSearch matterId="m1" />)

    expect(screen.queryByTestId("research-filters")).not.toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: /filters/i }))
    expect(screen.getByTestId("research-filters")).toBeInTheDocument()
    expect(screen.getByLabelText("Court filter")).toBeInTheDocument()
    expect(screen.getByLabelText("Jurisdiction filter")).toBeInTheDocument()
    expect(screen.getByLabelText("Year from")).toBeInTheDocument()
    expect(screen.getByLabelText("Year to")).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: /filters/i }))
    expect(screen.queryByTestId("research-filters")).not.toBeInTheDocument()
  })

  it("displays search results with relevance scores", async () => {
    mockApiFetch.mockResolvedValue(searchResponse)
    const onSearchComplete = vi.fn()
    const user = userEvent.setup()
    render(
      <ResearchSearch matterId="m1" onSearchComplete={onSearchComplete} />
    )

    await performSearch(user)

    await waitFor(() => {
      expect(screen.getByTestId("research-results")).toBeInTheDocument()
    })
    expect(screen.getByText("Roe v. Wade")).toBeInTheDocument()
    expect(screen.getByText("Brown v. Board of Education")).toBeInTheDocument()
    expect(screen.getByText("410 U.S. 113")).toBeInTheDocument()
    expect(screen.getByText("347 U.S. 483")).toBeInTheDocument()
    expect(screen.getByLabelText("Relevance score 95%")).toBeInTheDocument()
    expect(screen.getByLabelText("Relevance score 50%")).toBeInTheDocument()
    expect(onSearchComplete).toHaveBeenCalledWith(results)
  })

  it("shows a loading spinner while the search is in flight", async () => {
    let resolveSearch!: (value: unknown) => void
    mockApiFetch.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveSearch = resolve
        })
    )
    const user = userEvent.setup()
    render(<ResearchSearch matterId="m1" />)

    await performSearch(user)

    expect(screen.getByTestId("research-loading")).toBeInTheDocument()

    resolveSearch({
      results: [],
      total_results: 0,
      query_used: "negligence",
    })

    await waitFor(() => {
      expect(screen.queryByTestId("research-loading")).not.toBeInTheDocument()
    })
  })

  it("renders an empty state when no results match", async () => {
    mockApiFetch.mockResolvedValue({
      results: [],
      total_results: 0,
      query_used: "negligence",
    })
    const user = userEvent.setup()
    render(<ResearchSearch matterId="m1" />)

    await performSearch(user)

    await waitFor(() => {
      expect(screen.getByTestId("research-empty")).toBeInTheDocument()
    })
    expect(screen.getByText("No results found")).toBeInTheDocument()
  })

  it("renders an error state with a retry button when the API fails", async () => {
    mockApiFetch.mockRejectedValue(new Error("Search failed: 500"))
    const user = userEvent.setup()
    render(<ResearchSearch matterId="m1" />)

    await performSearch(user)

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("Search failed: 500")
    })
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument()
  })

  it("expands a result card on click", async () => {
    mockApiFetch.mockResolvedValue(searchResponse)
    const user = userEvent.setup()
    render(<ResearchSearch matterId="m1" />)

    await performSearch(user)

    const card = await screen.findByRole("button", { name: /Roe v. Wade/i })
    expect(card).toHaveAttribute("aria-expanded", "false")

    await user.click(card)
    expect(card).toHaveAttribute("aria-expanded", "true")

    await user.click(card)
    expect(card).toHaveAttribute("aria-expanded", "false")
  })

  it("calls onGenerateBrief with the query used for the search", async () => {
    mockApiFetch.mockResolvedValue(searchResponse)
    const onGenerateBrief = vi.fn()
    const user = userEvent.setup()
    render(<ResearchSearch matterId="m1" onGenerateBrief={onGenerateBrief} />)

    await performSearch(user)

    const generateButton = await screen.findByRole("button", {
      name: /generate brief/i,
    })
    await user.click(generateButton)
    expect(onGenerateBrief).toHaveBeenCalledWith("negligence")
  })
})
