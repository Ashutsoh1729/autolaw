import { useState, useCallback, useEffect, useRef, Fragment } from "react"
import {
  Loader2,
  RefreshCw,
  Copy,
  Check,
  ChevronDown,
  ChevronUp,
  AlertCircle,
  ExternalLink,
  FileText,
  Sparkles,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import type { ResearchBrief } from "@/hooks/useResearch"
import { cn } from "@/lib/utils"

const PASSAGE_TRUNCATE_LENGTH = 500

interface ResearchBriefProps {
  matterId: string
  brief: ResearchBrief | null
  status: string
  loading: boolean
  error: string | null
  onRegenerate: (query?: string) => void
}

interface ExpandedCitation {
  sectionIndex: number
  citationIndex: number
}

// ---------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------

function formatDate(iso: string | undefined): string {
  if (!iso) return ""
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ""
  return d.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  })
}

function ScoreBar({ score }: { score: number }) {
  const pct = Math.max(0, Math.min(100, Math.round(score * 100)))
  return (
    <div className="flex items-center gap-2" aria-label={`Relevance score ${pct}%`}>
      <span className="text-xs text-muted-foreground">Relevance</span>
      <div className="h-2 w-20 rounded-full bg-muted overflow-hidden">
        <div
          className={cn(
            "h-full rounded-full",
            pct > 70 ? "bg-green-500" : pct >= 40 ? "bg-yellow-500" : "bg-red-500"
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-muted-foreground tabular-nums">{pct}%</span>
    </div>
  )
}

/** Render basic markdown inline styles: **bold** and *italic*. */
function renderInlineText(text: string): React.ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((segment, idx) => {
    if (segment.startsWith("**") && segment.endsWith("**")) {
      return <strong key={idx}>{segment.slice(2, -2)}</strong>
    }
    return (
      <Fragment key={idx}>
        {segment.split(/(\*[^*]+\*)/g).map((s, j) => {
          if (s.startsWith("*") && s.endsWith("*") && s.length > 2) {
            return <em key={j}>{s.slice(1, -1)}</em>
          }
          return s
        })}
      </Fragment>
    )
  })
}

/** Render a content string with inline numbered citation buttons `[1]`, `[2]`, ... */
function renderContentWithCitations(
  content: string,
  onCite: (citationIndex: number) => void
): React.ReactNode[] {
  const nodes: React.ReactNode[] = []
  let listBuffer: string[] = []

  const renderInline = (text: string, key: string): React.ReactNode => {
    const segments = text.split(/(\[\d+\])/g)
    return segments.map((segment, idx) => {
      const match = segment.match(/^\[(\d+)\]$/)
      if (match) {
        const n = parseInt(match[1], 10)
        return (
          <button
            key={`${key}-cite-${idx}`}
            type="button"
            onClick={() => onCite(n - 1)}
            title={`Citation ${n}`}
            className="mx-0.5 inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-primary/10 px-1 text-[10px] font-semibold text-primary align-baseline hover:bg-primary/20"
          >
            {n}
          </button>
        )
      }
      return <Fragment key={`${key}-seg-${idx}`}>{renderInlineText(segment)}</Fragment>
    })
  }

  const flushList = (key: string) => {
    if (listBuffer.length > 0) {
      nodes.push(
        <ul key={key} className="list-disc pl-5 space-y-1 my-1">
          {listBuffer.map((item, i) => (
            <li key={i}>{renderInline(item, `${key}-li-${i}`)}</li>
          ))}
        </ul>
      )
      listBuffer = []
    }
  }

  content.split("\n").forEach((line, i) => {
    const trimmed = line.trim()
    const key = `block-${i}`
    if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
      listBuffer.push(trimmed.slice(2))
      return
    }
    flushList(`ul-${i}`)
    if (!trimmed) {
      nodes.push(<div key={key} className="h-2" />)
      return
    }
    if (trimmed.startsWith("### ")) {
      nodes.push(
        <h4 key={key} className="mt-2 text-sm font-semibold">
          {renderInline(trimmed.slice(4), key)}
        </h4>
      )
    } else if (trimmed.startsWith("## ")) {
      nodes.push(
        <h3 key={key} className="mt-2 text-sm font-semibold">
          {renderInline(trimmed.slice(3), key)}
        </h3>
      )
    } else {
      nodes.push(
        <p key={key} className="text-sm leading-relaxed">
          {renderInline(trimmed, key)}
        </p>
      )
    }
  })
  flushList(`ul-${content.split("\n").length}`)

  return nodes
}

function briefToText(brief: ResearchBrief): string {
  const lines: string[] = []
  lines.push(`Research Brief: ${brief.query}`)
  lines.push(`Status: ${brief.status}`)
  if (brief.created_at) lines.push(`Generated: ${brief.created_at}`)
  lines.push("")
  lines.push("Summary")
  lines.push(brief.summary)
  for (const section of brief.sections) {
    lines.push("")
    lines.push(section.title)
    lines.push(section.content)
    if (section.citations.length > 0) {
      lines.push("")
      lines.push("References:")
      section.citations.forEach((c, i) => {
        lines.push(`[${i + 1}] ${c.citation}${c.passage ? ` — ${c.passage}` : ""}`)
      })
    }
  }
  return lines.join("\n")
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ResearchBrief({
  matterId,
  brief,
  status,
  loading,
  error,
  onRegenerate,
}: ResearchBriefProps) {
  const [expandedSections, setExpandedSections] = useState<Set<number>>(new Set())
  const [expandedCitation, setExpandedCitation] = useState<ExpandedCitation | null>(null)
  const [expandedPassages, setExpandedPassages] = useState<Set<string>>(new Set())
  const [showRegenerateDialog, setShowRegenerateDialog] = useState(false)
  const [copied, setCopied] = useState(false)
  const copyTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const lastBriefId = useRef<string | null>(null)

  // Default: all sections expanded when a (new) brief is available.
  useEffect(() => {
    if (brief && brief.id !== lastBriefId.current) {
      lastBriefId.current = brief.id
      setExpandedSections(new Set(brief.sections.map((_, i) => i)))
    }
  }, [brief])

  useEffect(() => {
    return () => {
      if (copyTimer.current) clearTimeout(copyTimer.current)
    }
  }, [])

  const toggleSection = useCallback((index: number) => {
    setExpandedSections((prev) => {
      const next = new Set(prev)
      if (next.has(index)) next.delete(index)
      else next.add(index)
      return next
    })
  }, [])

  const toggleCitation = useCallback((sectionIndex: number, citationIndex: number) => {
    setExpandedCitation((prev) =>
      prev &&
      prev.sectionIndex === sectionIndex &&
      prev.citationIndex === citationIndex
        ? null
        : { sectionIndex, citationIndex }
    )
  }, [])

  const togglePassage = useCallback((key: string) => {
    setExpandedPassages((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }, [])

  const handleCopy = useCallback(async () => {
    if (!brief) return
    try {
      await navigator.clipboard.writeText(briefToText(brief))
      setCopied(true)
      if (copyTimer.current) clearTimeout(copyTimer.current)
      copyTimer.current = setTimeout(() => setCopied(false), 2000)
    } catch {
      // Clipboard unavailable (e.g. non-secure context) — ignore.
    }
  }, [brief])

  const handleRegenerateConfirm = useCallback(() => {
    setShowRegenerateDialog(false)
    onRegenerate(brief?.query)
  }, [brief?.query, onRegenerate])

  // --- not generated -------------------------------------------------------
  if (status === "not_generated") {
    return (
      <Card data-testid="brief-not-generated">
        <CardContent className="py-10 text-center">
          <FileText className="mx-auto h-10 w-10 text-muted-foreground mb-3" />
          <p className="text-sm text-muted-foreground">
            No brief generated yet. Search for relevant cases and generate a brief.
          </p>
        </CardContent>
      </Card>
    )
  }

  // --- generating ----------------------------------------------------------
  if (status === "generating") {
    return (
      <Card data-testid="brief-generating">
        <CardContent className="py-10 text-center">
          <Loader2 className="mx-auto h-8 w-8 animate-spin text-primary mb-3" />
          <p className="text-sm font-medium">Analyzing passages...</p>
          <p className="text-xs text-muted-foreground mt-1">
            Synthesizing legal research into a structured brief. This can take a minute.
          </p>
        </CardContent>
      </Card>
    )
  }

  // --- no results ----------------------------------------------------------
  if (status === "no_results") {
    return (
      <Card data-testid="brief-no-results">
        <CardContent className="py-10 text-center">
          <AlertCircle className="mx-auto h-8 w-8 text-muted-foreground mb-3" />
          <p className="text-sm text-muted-foreground">
            No relevant precedents found for this matter.
          </p>
        </CardContent>
      </Card>
    )
  }

  // --- error ---------------------------------------------------------------
  if (status === "error") {
    return (
      <Card data-testid="brief-error" className="border-destructive/30">
        <CardContent className="py-8 flex items-start gap-3" role="alert">
          <AlertCircle className="h-5 w-5 text-destructive shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-medium text-destructive">Brief generation failed</p>
            {error && <p className="text-sm text-destructive/90 mt-1">{error}</p>}
          </div>
        </CardContent>
      </Card>
    )
  }

  // --- complete / partial --------------------------------------------------
  const isPartial = status === "partial"
  const briefToShow = brief

  if (!briefToShow) {
    return (
      <Card>
        <CardContent className="py-10 text-center text-muted-foreground">
          {loading ? "Loading brief..." : "Brief unavailable."}
        </CardContent>
      </Card>
    )
  }

  const statusVariant = isPartial ? "warning" : "success"

  return (
    <div className="space-y-4" data-testid="brief-complete">
      {/* Metadata + actions */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-lg font-semibold">Research Brief</h3>
              <Badge variant={statusVariant}>
                {isPartial ? "Partial" : "Complete"}
              </Badge>
            </div>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={() => void handleCopy()}>
                {copied ? (
                  <Check className="h-4 w-4 text-green-600" />
                ) : (
                  <Copy className="h-4 w-4" />
                )}
                {copied ? "Copied" : "Copy brief"}
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowRegenerateDialog(true)}
                disabled={loading}
              >
                <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />
                Regenerate
              </Button>
            </div>
          </div>

          <div className="mt-3 space-y-1 text-sm">
            <p className="text-muted-foreground">
              Query: <span className="font-medium text-foreground">{briefToShow.query}</span>
            </p>
            <p className="text-xs text-muted-foreground">
              Generated {formatDate(briefToShow.created_at)}
            </p>
          </div>

          {isPartial && (
            <div
              className="mt-4 rounded-md border border-yellow-300 bg-yellow-50 px-4 py-3 text-sm text-yellow-900 dark:border-yellow-800 dark:bg-yellow-950 dark:text-yellow-100"
              data-testid="brief-partial-warning"
            >
              Some sections could not be completed. The brief may be incomplete.
            </div>
          )}
        </CardContent>
      </Card>

      {/* Summary */}
      <Card>
        <CardContent className="pt-6">
          <h4 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-2">
            Summary
          </h4>
          <blockquote className="border-l-4 border-primary/40 bg-muted/40 rounded-r-md px-4 py-3 text-sm leading-relaxed">
            {briefToShow.summary}
          </blockquote>
        </CardContent>
      </Card>

      {/* Sections */}
      {briefToShow.sections.map((section, sectionIndex) => {
        const isExpanded = expandedSections.has(sectionIndex)
        return (
          <Card key={`${section.title}-${sectionIndex}`} data-testid="brief-section">
            <CardContent className="pt-4">
              <div className="flex items-center justify-between">
                <h4 className="font-semibold">{section.title}</h4>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => toggleSection(sectionIndex)}
                  aria-expanded={isExpanded}
                >
                  {isExpanded ? (
                    <ChevronUp className="h-4 w-4" />
                  ) : (
                    <ChevronDown className="h-4 w-4" />
                  )}
                  {isExpanded ? "Collapse" : "Expand"}
                </Button>
              </div>

              {isExpanded && (
                <div className="mt-3 space-y-3">
                  <div className="space-y-1">
                    {renderContentWithCitations(section.content, (citationIndex) =>
                      toggleCitation(sectionIndex, citationIndex)
                    )}
                  </div>

                  {/* Expanded citation detail */}
                  {expandedCitation &&
                    expandedCitation.sectionIndex === sectionIndex &&
                    section.citations[expandedCitation.citationIndex] && (
                      <CitationCard
                        citation={section.citations[expandedCitation.citationIndex]}
                        passageExpanded={expandedPassages.has(
                          `${sectionIndex}:${expandedCitation.citationIndex}`
                        )}
                        onTogglePassage={() =>
                          togglePassage(`${sectionIndex}:${expandedCitation.citationIndex}`)
                        }
                        matterId={matterId}
                      />
                    )}

                  {/* References list */}
                  {section.citations.length > 0 && (
                    <div className="border-t pt-3">
                      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">
                        References
                      </p>
                      <ul className="space-y-1.5">
                        {section.citations.map((citation, citationIndex) => {
                          const isOpen =
                            expandedCitation?.sectionIndex === sectionIndex &&
                            expandedCitation.citationIndex === citationIndex
                          return (
                            <li key={citation.citation || citationIndex}>
                              <button
                                type="button"
                                className="inline-flex items-center gap-2 text-sm text-primary hover:underline"
                                onClick={() => toggleCitation(sectionIndex, citationIndex)}
                                aria-expanded={isOpen}
                              >
                                <span className="inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-primary/10 px-1 text-[10px] font-semibold text-primary">
                                  {citationIndex + 1}
                                </span>
                                <span className="font-medium">{citation.citation}</span>
                              </button>
                            </li>
                          )
                        })}
                      </ul>
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        )
      })}

      {/* Regenerate confirmation */}
      <Dialog open={showRegenerateDialog} onOpenChange={setShowRegenerateDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Regenerate brief?</DialogTitle>
            <DialogDescription>
              This will replace the current brief. Any changes will be lost.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowRegenerateDialog(false)}>
              Cancel
            </Button>
            <Button onClick={handleRegenerateConfirm}>
              <Sparkles className="h-4 w-4" />
              Regenerate
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Citation card (inline expanded detail)
// ---------------------------------------------------------------------------

interface CitationCardProps {
  citation: {
    citation: string
    passage: string
    relevance_score: number
    corpus_document_id: string
  }
  passageExpanded: boolean
  onTogglePassage: () => void
  matterId: string
}

function CitationCard({
  citation,
  passageExpanded,
  onTogglePassage,
  matterId,
}: CitationCardProps) {
  const truncated = citation.passage.length > PASSAGE_TRUNCATE_LENGTH && !passageExpanded
  const shown = truncated
    ? `${citation.passage.slice(0, PASSAGE_TRUNCATE_LENGTH)}...`
    : citation.passage

  return (
    <div
      className="rounded-md border bg-muted/40 p-3 space-y-2"
      data-testid="citation-card"
    >
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm font-medium">{citation.citation}</p>
        <a
          href={`/matters/${matterId}`}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline shrink-0"
        >
          <ExternalLink className="h-3 w-3" />
          View Source
        </a>
      </div>
      {shown && (
        <p className="text-xs text-muted-foreground leading-relaxed whitespace-pre-line">
          {shown}
        </p>
      )}
      <div className="flex items-center justify-between">
        <ScoreBar score={citation.relevance_score} />
        {citation.passage.length > PASSAGE_TRUNCATE_LENGTH && (
          <Button
            variant="ghost"
            size="sm"
            className="h-6 px-2 text-xs"
            onClick={onTogglePassage}
            aria-expanded={passageExpanded}
          >
            {passageExpanded ? "Show less" : "Show more"}
          </Button>
        )}
      </div>
    </div>
  )
}
