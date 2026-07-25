import { useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import { Plus, Search, FileText, ArrowRight } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { MatterProgressBar } from "@/components/ProgressBar"
import { useMatters, type Matter } from "@/hooks/useMatter"

export function Dashboard() {
  const navigate = useNavigate()
  const [search, setSearch] = useState("")
  const [statusFilter, setStatusFilter] = useState<string>("")
  const { matters, total, loading, error } = useMatters(search || undefined, statusFilter || undefined)

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold">My Matters</h1>
          <p className="text-muted-foreground mt-1">
            {total} matter{total !== 1 ? "s" : ""} total
          </p>
        </div>
        <Button onClick={() => navigate("/matters/new")}>
          <Plus className="h-4 w-4 mr-2" />
          New Matter
        </Button>
      </div>

      {/* Search & Filter */}
      <div className="flex items-center gap-4 mb-6">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search by title or case number..."
            className="pl-9"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <select
          className="h-9 rounded-md border border-input bg-background px-3 text-sm"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
        >
          <option value="">All Status</option>
          <option value="active">Active</option>
          <option value="archived">Archived</option>
        </select>
      </div>

      {/* Loading */}
      {loading && (
        <div className="text-center py-12 text-muted-foreground">Loading matters...</div>
      )}

      {/* Error */}
      {error && (
        <div className="text-center py-12 text-red-600 bg-red-50 rounded-lg">
          {error}
        </div>
      )}

      {/* Empty state */}
      {!loading && !error && matters.length === 0 && (
        <Card className="text-center py-12">
          <CardContent>
            <FileText className="mx-auto h-12 w-12 text-muted-foreground mb-4" />
            <h3 className="text-lg font-semibold mb-2">No matters yet</h3>
            <p className="text-muted-foreground mb-6">
              Create your first matter to start organizing case documents and
              building timelines.
            </p>
            <Button onClick={() => navigate("/matters/new")}>
              <Plus className="h-4 w-4 mr-2" />
              Create Your First Matter
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Matter cards */}
      {!loading && matters.length > 0 && (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {matters.map((matter) => (
            <MatterCard key={matter.id} matter={matter} />
          ))}
        </div>
      )}
    </div>
  )
}

function MatterCard({ matter }: { matter: Matter }) {
  return (
    <Link to={`/matters/${matter.id}`}>
      <Card className="hover:shadow-md transition-shadow cursor-pointer h-full">
        <CardHeader>
          <div className="flex items-start justify-between">
            <div className="space-y-1">
              <CardTitle className="text-base">{matter.title}</CardTitle>
              {matter.case_number && (
                <CardDescription>{matter.case_number}</CardDescription>
              )}
            </div>
            <Badge
              variant={matter.status === "active" ? "success" : "secondary"}
            >
              {matter.status}
            </Badge>
          </div>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {matter.case_type && (
              <div className="text-sm">
                <span className="text-muted-foreground">Type:</span>{" "}
                {matter.case_type}
              </div>
            )}
            {matter.jurisdiction && (
              <div className="text-sm">
                <span className="text-muted-foreground">Jurisdiction:</span>{" "}
                {matter.jurisdiction}
              </div>
            )}
            <MatterProgressBar
              total={matter.document_count}
              processed={matter.processed_count}
            />
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>{matter.document_count} document(s)</span>
              <ArrowRight className="h-3 w-3" />
            </div>
          </div>
        </CardContent>
      </Card>
    </Link>
  )
}
