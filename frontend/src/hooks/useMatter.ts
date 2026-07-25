import { useState, useEffect, useCallback } from "react"

export interface Matter {
  id: string
  title: string
  case_number?: string
  case_type?: string
  jurisdiction?: string
  description?: string
  status: string
  email_address?: string
  created_at: string
  updated_at: string
  document_count: number
  processed_count: number
}

export interface Document {
  id: string
  matter_id: string
  filename: string
  original_type: string
  file_size_bytes: number
  doc_type?: string
  processing_status: string
  processing_error?: string
  page_count?: number
  uploaded_at: string
}

export interface TimelineEvent {
  id: string
  matter_id: string
  source_document_id: string
  source_chunk_index?: number
  date: string
  date_precision: string
  date_end?: string
  title: string
  description?: string
  people: string[]
  doc_reference?: string
  confidence: number
  dedup_group?: string
  source_filename?: string
}

const API_BASE = "/api"

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `Request failed: ${res.status}`)
  }
  return res.json()
}

export function useMatters(search?: string, status?: string) {
  const [matters, setMatters] = useState<Matter[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchMatters = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams()
      if (search) params.set("search", search)
      if (status) params.set("status", status)
      const data = await apiFetch<{ matters: Matter[]; total: number }>(
        `/matters?${params.toString()}`
      )
      setMatters(data.matters)
      setTotal(data.total)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load matters")
    } finally {
      setLoading(false)
    }
  }, [search, status])

  useEffect(() => {
    fetchMatters()
  }, [fetchMatters])

  return { matters, total, loading, error, refetch: fetchMatters }
}

export function useMatter(matterId: string | undefined) {
  const [matter, setMatter] = useState<Matter | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!matterId) return
    setLoading(true)
    apiFetch<Matter>(`/matters/${matterId}`)
      .then(setMatter)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [matterId])

  return { matter, loading, error }
}

export function useDocuments(matterId: string | undefined) {
  const [documents, setDocuments] = useState<Document[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchDocs = useCallback(async () => {
    if (!matterId) return
    setLoading(true)
    try {
      const data = await apiFetch<{ documents: Document[]; total: number }>(
        `/matters/${matterId}/documents`
      )
      setDocuments(data.documents)
      setTotal(data.total)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load documents")
    } finally {
      setLoading(false)
    }
  }, [matterId])

  useEffect(() => {
    fetchDocs()
  }, [fetchDocs])

  return { documents, total, loading, error, refetch: fetchDocs }
}

export function useTimeline(
  matterId: string | undefined,
  filters?: { date_from?: string; date_to?: string; person?: string; search?: string }
) {
  const [events, setEvents] = useState<TimelineEvent[]>([])
  const [totalEvents, setTotalEvents] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!matterId) return
    setLoading(true)
    const params = new URLSearchParams()
    if (filters?.date_from) params.set("date_from", filters.date_from)
    if (filters?.date_to) params.set("date_to", filters.date_to)
    if (filters?.person) params.set("person", filters.person)
    if (filters?.search) params.set("search", filters.search)

    apiFetch<{ events: TimelineEvent[]; total_events: number }>(
      `/matters/${matterId}/timeline?${params.toString()}`
    )
      .then((data) => {
        setEvents(data.events)
        setTotalEvents(data.total_events)
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [matterId, filters?.date_from, filters?.date_to, filters?.person, filters?.search])

  return { events, totalEvents, loading, error }
}

export async function createMatter(data: {
  title: string
  case_number?: string
  case_type?: string
  jurisdiction?: string
  description?: string
}): Promise<Matter> {
  return apiFetch<Matter>("/matters", {
    method: "POST",
    body: JSON.stringify(data),
  })
}

export async function processDocument(matterId: string, docId: string) {
  return apiFetch<{ status: string; message: string }>(
    `/matters/${matterId}/documents/${docId}/process`,
    { method: "POST" }
  )
}

export async function exportTimeline(matterId: string, format: "docx" | "pdf") {
  const res = await fetch(`${API_BASE}/matters/${matterId}/export?format=${format}`)
  if (!res.ok) throw new Error("Export failed")
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = `timeline_${matterId}.${format}`
  a.click()
  URL.revokeObjectURL(url)
}
