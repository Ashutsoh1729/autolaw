import { useState, useCallback } from "react"
import {
  Search,
  SlidersHorizontal,
  Loader2,
  ChevronDown,
  ChevronUp,
  AlertCircle,
  FileSearch,
  Sparkles,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardContent } from "@/components/ui/card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  useResearchSearch,
  type SearchResultItem,
  type ResearchFilters,
} from "@/hooks/useResearch"
import { cn } from "@/lib/utils"

const COURT_OPTIONS = [
  "Supreme Court",
  "Court of Appeals",
  "Circuit Court",
  "District Court",
  "State Court",
]

interface ResearchSearchProps {
  matterId: string
  onSearchComplete?: (results: SearchResultItem[]) => void
  onGenerateBrief?: (query: string) => void
}

function ScoreBar({ score }: { score: number }) {
  const pct = Math.max(0, Math.min(100, Math.round(score * 100)))
  return (
    <div className="flex items-center gap-2">
      <div className="flex items-center gap-1" aria-label={`Relevance score ${pct}%`}>
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
    </div>
  )
}

export function ResearchSearch({
  matterId,
  onSearchComplete,
  onGenerateBrief,
}: ResearchSearchProps) {
  const { results, totalResults, loading, error, search } = useResearchSearch(matterId)

  const [query, setQuery] = useState("")
  const [lastQuery, setLastQuery] = useState("")
  const [showFilters, setShowFilters] = useState(false)
  const [court, setCourt] = useState("")
  const [jurisdiction, setJurisdiction] = useState("")
  const [yearFrom, setYearFrom] = useState("")
  const [yearTo, setYearTo] = useState("")
  const [expandedResultId, setExpandedResultId] = useState<string | null>(null)

  const handleSearch = useCallback(async () => {
    const trimmed = query.trim()
    if (!trimmed) return
    const filters: ResearchFilters = {}
    if (court) filters.court = court
    if (jurisdiction.trim()) filters.jurisdiction = jurisdiction.trim()
    if (yearFrom) filters.yearFrom = Number(yearFrom)
    if (yearTo) filters.yearTo = Number(yearTo)

    const data = await search(trimmed, Object.keys(filters).length > 0 ? filters : undefined)
    if (data) {
      setLastQuery(trimmed)
      setExpandedResultId(null)
      onSearchComplete?.(data.results)
    }
  }, [query, court, jurisdiction, yearFrom, yearTo, search, onSearchComplete])

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === "Enter") {
        void handleSearch()
      }
    },
    [handleSearch]
  )

  const handleGenerateBrief = useCallback(() => {
    if (!lastQuery) return
    onGenerateBrief?.(lastQuery)
  }, [lastQuery, onGenerateBrief])

  return (
    <Card>
      <CardContent className="pt-6 space-y-4">
        <div className="flex flex-col sm:flex-row gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              aria-label="Search query"
              placeholder="Search for cases, statutes, precedents..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              className="pl-9"
            />
          </div>
          <div className="flex gap-2">
            <Button
              variant="outline"
              type="button"
              aria-expanded={showFilters}
              onClick={() => setShowFilters((v) => !v)}
            >
              <SlidersHorizontal className="h-4 w-4" />
              Filters
            </Button>
            <Button
              type="button"
              onClick={() => void handleSearch()}
              disabled={!query.trim() || loading}
            >
              {loading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Search className="h-4 w-4" />
              )}
              Search
            </Button>
          </div>
        </div>

        {/* Filter controls (collapsible) */}
        {showFilters && (
          <div
            className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 rounded-md border bg-muted/40 p-3"
            data-testid="research-filters"
          >
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">Court</label>
              <Select value={court} onValueChange={setCourt}>
                <SelectTrigger aria-label="Court filter">
                  <SelectValue placeholder="Any court" />
                </SelectTrigger>
                <SelectContent>
                  {COURT_OPTIONS.map((c) => (
                    <SelectItem key={c} value={c}>
                      {c}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">
                Jurisdiction
              </label>
              <Input
                aria-label="Jurisdiction filter"
                placeholder="e.g. California"
                value={jurisdiction}
                onChange={(e) => setJurisdiction(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">Year from</label>
              <Input
                aria-label="Year from"
                type="number"
                placeholder="e.g. 2000"
                value={yearFrom}
                onChange={(e) => setYearFrom(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">Year to</label>
              <Input
                aria-label="Year to"
                type="number"
                placeholder="e.g. 2025"
                value={yearTo}
                onChange={(e) => setYearTo(e.target.value)}
              />
            </div>
          </div>
        )}

        {/* Error state */}
        {error && (
          <div
            className="flex items-start gap-3 rounded-md border border-destructive/30 bg-destructive/5 px-4 py-3"
            role="alert"
          >
            <AlertCircle className="h-4 w-4 text-destructive mt-0.5 shrink-0" />
            <div className="text-sm text-destructive flex-1">{error}</div>
            <Button variant="outline" size="sm" onClick={() => void handleSearch()}>
              Retry
            </Button>
          </div>
        )}

        {/* Loading state */}
        {loading && (
          <div
            className="flex items-center justify-center gap-2 py-8 text-muted-foreground"
            aria-live="polite"
            data-testid="research-loading"
          >
            <Loader2 className="h-5 w-5 animate-spin" />
            Searching legal corpus...
          </div>
        )}

        {/* Results */}
        {!loading && !error && results.length > 0 && (
          <div className="space-y-3" data-testid="research-results">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm text-muted-foreground">
                Found {totalResults} result{totalResults === 1 ? "" : "s"} for{" "}
                <span className="font-medium text-foreground">"{lastQuery}"</span>
              </p>
              {onGenerateBrief && (
                <Button size="sm" onClick={handleGenerateBrief}>
                  <Sparkles className="h-4 w-4" />
                  Generate Brief
                </Button>
              )}
            </div>

            <ul className="space-y-3">
              {results.map((item) => {
                const expanded = expandedResultId === item.chunk_id
                return (
                  <li key={item.chunk_id}>
                    <Card
                      className={cn(
                        "transition-shadow cursor-pointer hover:shadow-sm",
                        expanded && "ring-1 ring-primary/40"
                      )}
                    >
                      <CardContent className="pt-4 pb-3">
                        <button
                          type="button"
                          className="w-full text-left"
                          onClick={() =>
                            setExpandedResultId(expanded ? null : item.chunk_id)
                          }
                          aria-expanded={expanded}
                        >
                          <p className="font-semibold text-primary hover:underline">
                            {item.case_name || "Unnamed case"}
                          </p>
                          <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-muted-foreground mt-0.5">
                            {item.citation && <span>{item.citation}</span>}
                            {item.court && (
                              <>
                                <span aria-hidden>·</span>
                                <span>{item.court}</span>
                              </>
                            )}
                            {item.year ? (
                              <>
                                <span aria-hidden>·</span>
                                <span>{item.year}</span>
                              </>
                            ) : null}
                          </div>
                          <p
                            className={cn(
                              "text-sm text-muted-foreground mt-2 whitespace-pre-line",
                              !expanded && "line-clamp-3"
                            )}
                          >
                            {item.text}
                          </p>
                        </button>
                        <div className="flex items-center justify-between mt-3">
                          <ScoreBar score={item.relevance_score} />
                          <span className="text-xs text-muted-foreground inline-flex items-center gap-1">
                            {expanded ? (
                              <>
                                Show less <ChevronUp className="h-3 w-3" />
                              </>
                            ) : (
                              <>
                                Show more <ChevronDown className="h-3 w-3" />
                              </>
                            )}
                          </span>
                        </div>
                      </CardContent>
                    </Card>
                  </li>
                )
              })}
            </ul>
          </div>
        )}

        {/* Empty state (searched, no results) */}
        {!loading && !error && lastQuery && results.length === 0 && (
          <div
            className="flex flex-col items-center justify-center gap-2 py-8 text-center"
            data-testid="research-empty"
          >
            <FileSearch className="h-8 w-8 text-muted-foreground" />
            <p className="text-sm font-medium">No results found</p>
            <p className="text-sm text-muted-foreground max-w-md">
              Try a different query or adjust your filters (court, jurisdiction, year
              range).
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
