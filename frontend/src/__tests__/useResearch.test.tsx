import { describe, it, expect, vi, afterEach } from "vitest"
import { renderHook, act, waitFor } from "@testing-library/react"
import { useResearchSearch, useResearchBrief } from "@/hooks/useResearch"
import { apiFetch } from "@/lib/api"
import type {
  ResearchBrief,
  ResearchSearchResponse,
  ResearchStatusResponse,
} from "@/hooks/useResearch"

vi.mock("@/lib/api", () => ({
  apiFetch: vi.fn(),
}))

const mockApiFetch = vi.mocked(apiFetch)

const searchResponse: ResearchSearchResponse = {
  results: [
    {
      chunk_id: "c1",
      corpus_document_id: "d1",
      text: "The defendant owed a duty of care to the plaintiff.",
      case_name: "Roe v. Wade",
      citation: "410 U.S. 113",
      court: "Supreme Court",
      year: 1973,
      relevance_score: 0.95,
    },
  ],
  total_results: 1,
  query_used: "negligence liability",
}

const completeBrief: ResearchBrief = {
  id: "b1",
  matter_id: "m1",
  query: "negligence liability",
  created_at: "2025-01-01T00:00:00Z",
  summary: "Summary of the matter.",
  sections: [
    {
      title: "Key Precedents",
      content: "The court held that negligence requires a duty of care. [1]",
      citations: [
        {
          citation: "Roe v. Wade, 410 U.S. 113 (1973)",
          passage: "The defendant owed a duty of care.",
          relevance_score: 0.9,
          corpus_document_id: "d1",
        },
      ],
    },
  ],
  status: "complete",
}

afterEach(() => {
  vi.useRealTimers()
})

describe("useResearchSearch", () => {
  it("calls the search endpoint with the query and returns results", async () => {
    mockApiFetch.mockResolvedValue(searchResponse)
    const { result } = renderHook(() => useResearchSearch("m1"))

    let returned: ResearchSearchResponse | null | undefined = null
    await act(async () => {
      returned = await result.current.search("negligence")
    })

    expect(mockApiFetch).toHaveBeenCalledTimes(1)
    const [url, options] = mockApiFetch.mock.calls[0]
    expect(url).toBe("/api/matters/m1/research/search")
    expect(options?.method).toBe("POST")
    expect(JSON.parse(String(options?.body))).toEqual({
      query: "negligence",
      top_k: 10,
    })

    expect(returned).toEqual(searchResponse)
    expect(result.current.results).toEqual(searchResponse.results)
    expect(result.current.totalResults).toBe(1)
    expect(result.current.loading).toBe(false)
    expect(result.current.error).toBeNull()
  })

  it("includes filters in the request body when provided", async () => {
    mockApiFetch.mockResolvedValue(searchResponse)
    const { result } = renderHook(() => useResearchSearch("m1"))

    await act(async () => {
      await result.current.search("negligence", {
        court: "Supreme Court",
        jurisdiction: "US",
        yearFrom: 2000,
        yearTo: 2025,
      })
    })

    const [, options] = mockApiFetch.mock.calls[0]
    expect(JSON.parse(String(options?.body))).toEqual({
      query: "negligence",
      filters: {
        court: "Supreme Court",
        jurisdiction: "US",
        yearFrom: 2000,
        yearTo: 2025,
      },
      top_k: 10,
    })
  })

  it("sets an error and clears results when the API fails", async () => {
    mockApiFetch.mockRejectedValue(new Error("Search API error"))
    const { result } = renderHook(() => useResearchSearch("m1"))

    await act(async () => {
      await result.current.search("negligence")
    })

    expect(result.current.error).toBe("Search API error")
    expect(result.current.results).toEqual([])
    expect(result.current.totalResults).toBe(0)
    expect(result.current.loading).toBe(false)
  })
})

describe("useResearchBrief", () => {
  it("fetches the initial status on mount", async () => {
    mockApiFetch.mockResolvedValue({
      brief_id: null,
      status: "not_generated",
    } satisfies ResearchStatusResponse)
    const { result } = renderHook(() => useResearchBrief("m1"))

    await waitFor(() => {
      expect(result.current.status).toBe("not_generated")
    })
    expect(mockApiFetch).toHaveBeenCalledWith("/api/matters/m1/research/status")
  })

  it("generateBrief posts to the brief endpoint and stores the returned brief", async () => {
    mockApiFetch.mockResolvedValueOnce({
      brief_id: null,
      status: "not_generated",
    } satisfies ResearchStatusResponse)
    mockApiFetch.mockResolvedValueOnce(completeBrief)

    const { result } = renderHook(() => useResearchBrief("m1"))
    await waitFor(() => expect(result.current.status).toBe("not_generated"))

    await act(async () => {
      await result.current.generateBrief("negligence")
    })

    const [url, options] = mockApiFetch.mock.calls[1]
    expect(url).toBe("/api/matters/m1/research/brief")
    expect(options?.method).toBe("POST")
    expect(JSON.parse(String(options?.body))).toEqual({ query: "negligence" })

    expect(result.current.status).toBe("complete")
    expect(result.current.brief).toEqual(completeBrief)
    expect(result.current.loading).toBe(false)
  })

  it("regenerateBrief posts to the regenerate endpoint", async () => {
    mockApiFetch.mockResolvedValueOnce({
      brief_id: null,
      status: "not_generated",
    } satisfies ResearchStatusResponse)
    mockApiFetch.mockResolvedValueOnce(completeBrief)

    const { result } = renderHook(() => useResearchBrief("m1"))
    await waitFor(() => expect(result.current.status).toBe("not_generated"))

    await act(async () => {
      await result.current.regenerateBrief("breach of contract")
    })

    expect(mockApiFetch.mock.calls[1][0]).toBe(
      "/api/matters/m1/research/brief/regenerate"
    )
    expect(mockApiFetch.mock.calls[1][1]?.method).toBe("POST")
    expect(JSON.parse(String(mockApiFetch.mock.calls[1][1]?.body))).toEqual({
      query: "breach of contract",
    })
    expect(result.current.brief).toEqual(completeBrief)
  })

  it("polls status every 2s until a terminal status is reached", async () => {
    vi.useFakeTimers()

    const responses: unknown[] = [
      { brief_id: null, status: "not_generated" }, // mount: GET /status
      { ...completeBrief, status: "generating" }, // POST /brief
      { brief_id: "b1", status: "generating" }, // poll 1
      { brief_id: "b1", status: "generating" }, // poll 2
      { brief_id: "b1", status: "complete", brief: completeBrief }, // poll 3
    ]
    mockApiFetch.mockImplementation(() => Promise.resolve(responses.shift()))

    const { result } = renderHook(() => useResearchBrief("m1"))

    // Flush the mount effect (initial GET /status).
    await act(async () => {})
    expect(result.current.status).toBe("not_generated")

    // Trigger brief generation → response status is "generating".
    await act(async () => {
      await result.current.generateBrief("negligence")
    })
    expect(result.current.status).toBe("generating")
    expect(result.current.loading).toBe(true)

    const statusCalls = () =>
      mockApiFetch.mock.calls.filter(([url]) => url === "/api/matters/m1/research/status")
        .length

    // Poll 1 (+2s)
    await act(async () => {
      vi.advanceTimersByTime(2000)
    })
    expect(result.current.status).toBe("generating")
    expect(statusCalls()).toBe(2)

    // Poll 2 (+4s)
    await act(async () => {
      vi.advanceTimersByTime(2000)
    })
    expect(statusCalls()).toBe(3)

    // Poll 3 (+6s) → terminal "complete"
    await act(async () => {
      vi.advanceTimersByTime(2000)
    })
    expect(result.current.status).toBe("complete")
    expect(result.current.brief).toEqual(completeBrief)
    expect(result.current.loading).toBe(false)

    // Polling must stop — no more status calls after advancing time.
    const callsAfterTerminal = statusCalls()
    await act(async () => {
      vi.advanceTimersByTime(10000)
    })
    expect(statusCalls()).toBe(callsAfterTerminal)
  })

  it("sets status to error when generateBrief fails", async () => {
    mockApiFetch.mockResolvedValueOnce({
      brief_id: null,
      status: "not_generated",
    } satisfies ResearchStatusResponse)
    mockApiFetch.mockRejectedValueOnce(new Error("Brief API error"))

    const { result } = renderHook(() => useResearchBrief("m1"))
    await waitFor(() => expect(result.current.status).toBe("not_generated"))

    await act(async () => {
      await result.current.generateBrief("negligence")
    })

    expect(result.current.status).toBe("error")
    expect(result.current.error).toBe("Brief API error")
    expect(result.current.loading).toBe(false)
  })

  it("stops polling on unmount", async () => {
    vi.useFakeTimers()

    const responses: unknown[] = [
      { brief_id: null, status: "not_generated" },
      { ...completeBrief, status: "generating" },
    ]
    mockApiFetch.mockImplementation(() => Promise.resolve(responses.shift()))

    const { result, unmount } = renderHook(() => useResearchBrief("m1"))
    await act(async () => {})

    await act(async () => {
      await result.current.generateBrief("negligence")
    })
    expect(result.current.status).toBe("generating")

    unmount()
    const callsAfterUnmount = mockApiFetch.mock.calls.length
    await act(async () => {
      vi.advanceTimersByTime(10000)
    })
    expect(mockApiFetch.mock.calls.length).toBe(callsAfterUnmount)
  })
})
