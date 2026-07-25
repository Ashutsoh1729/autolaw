import { useState } from "react"
import { useParams, useNavigate } from "react-router-dom"
import {
  ArrowLeft,
  Search,
  Download,
  Calendar,
  User,
  FileText,
  ChevronDown,
  ChevronUp,
  Loader2,
  AlertCircle,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent } from "@/components/ui/card"
import { useTimeline, exportTimeline } from "@/hooks/useMatter"
import { useMatter } from "@/hooks/useMatter"

const PRECISION_LABELS: Record<string, string> = {
  exact: "",
  month: "(Month)",
  year: "(Year)",
  range: "(Date Range)",
}

const PRECISION_COLORS: Record<string, string> = {
  exact: "border-l-primary",
  month: "border-l-blue-400",
  year: "border-l-yellow-400",
  range: "border-l-purple-400",
}

export function TimelineView() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { matter } = useMatter(id)

  const [search, setSearch] = useState("")
  const [dateFrom, setDateFrom] = useState("")
  const [dateTo, setDateTo] = useState("")
  const [person, setPerson] = useState("")

  const { events, totalEvents, loading, error } = useTimeline(id, {
    search: search || undefined,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
    person: person || undefined,
  })

  const [expandedId, setExpandedId] = useState<string | null>(null)

  const handleExport = async (format: "docx" | "pdf") => {
    if (!id) return
    try {
      await exportTimeline(id, format)
    } catch (err) {
      console.error("Export failed", err)
    }
  }

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <Button
        variant="ghost"
        className="mb-6"
        onClick={() => navigate(`/matters/${id}`)}
      >
        <ArrowLeft className="h-4 w-4 mr-2" />
        Back to Matter
      </Button>

      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold">
          Timeline
          {matter && <span className="text-muted-foreground"> · {matter.title}</span>}
        </h1>
        <p className="text-muted-foreground mt-1">
          {totalEvents} event{totalEvents !== 1 ? "s" : ""} extracted
        </p>
      </div>

      {/* Filters */}
      <Card className="mb-6">
        <CardContent className="py-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search events..."
                className="pl-9"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <div className="relative">
              <Calendar className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="From date (YYYY-MM-DD)"
                className="pl-9"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
              />
            </div>
            <div className="relative">
              <Calendar className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="To date (YYYY-MM-DD)"
                className="pl-9"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
              />
            </div>
            <div className="relative">
              <User className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Person name..."
                className="pl-9"
                value={person}
                onChange={(e) => setPerson(e.target.value)}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Export buttons */}
      <div className="flex items-center gap-2 mb-6 justify-end">
        <Button variant="outline" size="sm" onClick={() => handleExport("docx")}>
          <Download className="h-4 w-4 mr-2" />
          Export to Word
        </Button>
        <Button variant="outline" size="sm" onClick={() => handleExport("pdf")}>
          <Download className="h-4 w-4 mr-2" />
          Export to PDF
        </Button>
      </div>

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      )}

      {/* Error */}
      {error && (
        <Card>
          <CardContent className="py-12 text-center">
            <AlertCircle className="mx-auto h-10 w-10 text-destructive mb-3" />
            <p className="text-destructive">{error}</p>
          </CardContent>
        </Card>
      )}

      {/* Empty state */}
      {!loading && !error && events.length === 0 && (
        <Card>
          <CardContent className="py-16 text-center">
            <FileText className="mx-auto h-12 w-12 text-muted-foreground mb-4" />
            <h3 className="text-lg font-semibold mb-2">No events extracted yet</h3>
            <p className="text-muted-foreground mb-4 max-w-md mx-auto">
              Documents are still processing. Go to the matter detail page and
              process documents to extract timeline events.
            </p>
            <Button onClick={() => navigate(`/matters/${id}`)}>
              Go to Matter Detail
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Timeline events */}
      {!loading && events.length > 0 && (
        <div className="relative">
          {/* Timeline line */}
          <div className="absolute left-6 top-0 bottom-0 w-0.5 bg-border" />

          <div className="space-y-4">
            {events.map((event) => {
              const isExpanded = expandedId === event.id

              return (
                <div key={event.id} className="relative pl-14">
                  {/* Timeline dot */}
                  <div
                    className={`absolute left-4 top-4 w-4 h-4 rounded-full border-2 bg-background ${
                      PRECISION_COLORS[event.date_precision] || "border-l-primary"
                    }`}
                  />

                  {/* Event card */}
                  <Card
                    className={`cursor-pointer transition-shadow hover:shadow-md ${
                      PRECISION_COLORS[event.date_precision]
                    } border-l-4`}
                    onClick={() =>
                      setExpandedId(isExpanded ? null : event.id)
                    }
                  >
                    <CardContent className="py-4">
                      <div className="flex items-start justify-between">
                        <div className="space-y-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-semibold text-primary">
                              {event.date}
                            </span>
                            {event.date_precision !== "exact" && (
                              <Badge variant="outline" className="text-xs">
                                {PRECISION_LABELS[event.date_precision]}
                              </Badge>
                            )}
                          </div>
                          <h3 className="font-medium">{event.title}</h3>
                          {isExpanded && event.description && (
                            <p className="text-sm text-muted-foreground mt-2">
                              {event.description}
                            </p>
                          )}
                        </div>
                        <div className="shrink-0 ml-4">
                          {isExpanded ? (
                            <ChevronUp className="h-4 w-4 text-muted-foreground" />
                          ) : (
                            <ChevronDown className="h-4 w-4 text-muted-foreground" />
                          )}
                        </div>
                      </div>

                      {/* Expanded details */}
                      {isExpanded && (
                        <div className="mt-3 pt-3 border-t space-y-2 text-sm">
                          {event.people.length > 0 && (
                            <div className="flex items-center gap-2">
                              <User className="h-3.5 w-3.5 text-muted-foreground" />
                              <span>{event.people.join(", ")}</span>
                            </div>
                          )}
                          {event.source_filename && (
                            <div className="flex items-center gap-2 text-muted-foreground">
                              <FileText className="h-3.5 w-3.5" />
                              <span>{event.source_filename}</span>
                              {event.doc_reference && (
                                <span>· {event.doc_reference}</span>
                              )}
                            </div>
                          )}
                          <div className="flex items-center gap-2 text-muted-foreground">
                            <span>Confidence:</span>
                            <div className="w-24 bg-secondary rounded-full h-1.5">
                              <div
                                className="bg-primary h-1.5 rounded-full"
                                style={{
                                  width: `${Math.round(event.confidence * 100)}%`,
                                }}
                              />
                            </div>
                            <span>{Math.round(event.confidence * 100)}%</span>
                          </div>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
