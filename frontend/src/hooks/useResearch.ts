import { useState, useEffect, useCallback, useRef } from "react"
import { apiFetch } from "@/lib/api"

// ---------------------------------------------------------------------------
// Types (Group B API contract — see docs/plan/pipeline/phase-2/)
// ---------------------------------------------------------------------------

export interface SearchResultItem {
  chunk_id: string
  corpus_document_id: string
  text: string
  case_name: string
  citation: string
  court: string
  year: number
  relevance_score: number
}

export interface BriefCitation {
  citation: string
  passage: string
  relevance_score: number
  corpus_document_id: string
}

export interface BriefSection {
  title: string
  content: string
  citations: BriefCitation[]
}

export interface ResearchBrief {
  id: string
  matter_id: string
  query: string
  created_at: string
  summary: string
  sections: BriefSection[]
  status: "complete" | "partial" | "no_results" | "generating"
}

export type BriefStatus =
  | "not_generated"
  | "generating"
  | "complete"
  | "partial"
  | "no_results"
  | "error"

export interface ResearchFilters {
  court?: string
  jurisdiction?: string
  yearFrom?: number
  yearTo?: number
}

export interface ResearchSearchResponse {
  results: SearchResultItem[]
  total_results: number
  query_used: string
}

export interface ResearchStatusResponse {
  brief_id: string | null
  status: BriefStatus
  brief?: ResearchBrief
}

export interface ResearchBriefResponse extends ResearchBrief {}

const TERMINAL_STATUSES: BriefStatus[] = ["complete", "partial", "no_results", "error"]
const POLL_INTERVAL_MS = 2000

function toErrorMessage(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback
}

// ---------------------------------------------------------------------------
// useResearchSearch
// ---------------------------------------------------------------------------

export function useResearchSearch(matterId: string | undefined) {
  const [results, setResults] = useState<SearchResultItem[]>([])
  const [totalResults, setTotalResults] = useState(0)
  const [queryUsed, setQueryUsed] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const search = useCallback(
    async (query: string, filters?: ResearchFilters) => {
      if (!matterId) return
      setLoading(true)
      setError(null)
      try {
        const data = await apiFetch<ResearchSearchResponse>(
          `/api/matters/${matterId}/research/search`,
          {
            method: "POST",
            body: JSON.stringify({ query, filters, top_k: 10 }),
          }
        )
        setResults(data.results)
        setTotalResults(data.total_results)
        setQueryUsed(data.query_used)
        return data
      } catch (err) {
        setResults([])
        setTotalResults(0)
        setError(toErrorMessage(err, "Search failed"))
        return null
      } finally {
        setLoading(false)
      }
    },
    [matterId]
  )

  const clearResults = useCallback(() => {
    setResults([])
    setTotalResults(0)
    setError(null)
  }, [])

  return { results, totalResults, queryUsed, loading, error, search, clearResults }
}

// ---------------------------------------------------------------------------
// useResearchBrief
// ---------------------------------------------------------------------------

export function useResearchBrief(matterId: string | undefined) {
  const [brief, setBrief] = useState<ResearchBrief | null>(null)
  const [status, setStatus] = useState<BriefStatus>("not_generated")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const stopPolling = useCallback(() => {
    if (pollTimer.current) {
      clearTimeout(pollTimer.current)
      pollTimer.current = null
    }
  }, [])

  // Poll status every POLL_INTERVAL_MS while the brief is generating.
  const pollStatus = useCallback(async () => {
    if (!matterId) return
    try {
      const data = await apiFetch<ResearchStatusResponse>(
        `/api/matters/${matterId}/research/status`
      )
      setStatus(data.status)
      if (data.brief) setBrief(data.brief)
      if (TERMINAL_STATUSES.includes(data.status)) {
        setLoading(false)
        return
      }
      pollTimer.current = setTimeout(() => {
        void pollStatus()
      }, POLL_INTERVAL_MS)
    } catch (err) {
      setError(toErrorMessage(err, "Failed to check brief status"))
      pollTimer.current = setTimeout(() => {
        void pollStatus()
      }, POLL_INTERVAL_MS)
    }
  }, [matterId])

  const startPolling = useCallback(() => {
    if (!matterId) return
    stopPolling()
    pollTimer.current = setTimeout(() => {
      void pollStatus()
    }, POLL_INTERVAL_MS)
  }, [matterId, pollStatus, stopPolling])

  // Clean up the polling timer on unmount.
  useEffect(() => stopPolling, [stopPolling])

  const fetchStatus = useCallback(async () => {
    if (!matterId) return
    setLoading(true)
    setError(null)
    stopPolling()
    try {
      const data = await apiFetch<ResearchStatusResponse>(
        `/api/matters/${matterId}/research/status`
      )
      setStatus(data.status)
      setBrief(data.brief ?? null)
      if (data.status === "generating") {
        startPolling()
      } else {
        setLoading(false)
      }
    } catch (err) {
      setError(toErrorMessage(err, "Failed to load research status"))
      setLoading(false)
    }
  }, [matterId, startPolling, stopPolling])

  // Load the current status when the matter changes so an existing brief
  // (or an in-progress generation) is reflected immediately.
  useEffect(() => {
    void fetchStatus()
    return stopPolling
  }, [fetchStatus, stopPolling])

  const generateBrief = useCallback(
    async (query?: string) => {
      if (!matterId) return
      setLoading(true)
      setError(null)
      setStatus("generating")
      stopPolling()
      try {
        const data = await apiFetch<ResearchBriefResponse>(
          `/api/matters/${matterId}/research/brief`,
          {
            method: "POST",
            body: JSON.stringify(query ? { query } : {}),
          }
        )
        setBrief(data)
        setStatus(data.status)
        if (data.status === "generating") {
          startPolling()
        } else {
          setLoading(false)
        }
      } catch (err) {
        setStatus("error")
        setError(toErrorMessage(err, "Failed to generate brief"))
        setLoading(false)
      }
    },
    [matterId, startPolling, stopPolling]
  )

  const regenerateBrief = useCallback(
    async (query?: string) => {
      if (!matterId) return
      setLoading(true)
      setError(null)
      setStatus("generating")
      stopPolling()
      try {
        const data = await apiFetch<ResearchBriefResponse>(
          `/api/matters/${matterId}/research/brief/regenerate`,
          {
            method: "POST",
            body: JSON.stringify(query ? { query } : {}),
          }
        )
        setBrief(data)
        setStatus(data.status)
        if (data.status === "generating") {
          startPolling()
        } else {
          setLoading(false)
        }
      } catch (err) {
        setStatus("error")
        setError(toErrorMessage(err, "Failed to regenerate brief"))
        setLoading(false)
      }
    },
    [matterId, startPolling, stopPolling]
  )

  return {
    brief,
    status,
    loading,
    error,
    fetchStatus,
    generateBrief,
    regenerateBrief,
  }
}
