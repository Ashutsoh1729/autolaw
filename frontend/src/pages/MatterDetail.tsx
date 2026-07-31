import { useState, useCallback } from "react"
import { useParams, useNavigate } from "react-router-dom"
import {
  ArrowLeft,
  Upload,
  RefreshCw,
  FileText,
  Clock,
  Loader2,
  Eye,
  BookOpen,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { DropZone, type FileEntry } from "@/components/DropZone"
import { ProcessingBadge } from "@/components/ProcessingBadge"
import { UploadProgressBar, MatterProgressBar } from "@/components/ProgressBar"
import { EmailForwardingSetup } from "@/components/EmailForwardingSetup"
import { ResearchSearch } from "@/components/ResearchSearch"
import { ResearchBrief } from "@/components/ResearchBrief"
import { useUpload } from "@/hooks/useUpload"
import { useMatter, useDocuments, processDocument } from "@/hooks/useMatter"
import { useResearchBrief } from "@/hooks/useResearch"

const DOC_TYPE_LABELS: Record<string, string> = {
  contract: "Contract",
  email: "Email",
  police_report: "Police Report",
  medical_record: "Medical Record",
  correspondence: "Correspondence",
  other: "Other",
}

export function MatterDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { matter, loading: matterLoading, error: matterError } = useMatter(id)
  const { documents, total, loading: docsLoading, refetch: refetchDocs } = useDocuments(id)
  const { uploads, uploadFiles } = useUpload()

  const [showUpload, setShowUpload] = useState(false)
  const [files, setFiles] = useState<FileEntry[]>([])
  const [uploading, setUploading] = useState(false)
  const [processingDocId, setProcessingDocId] = useState<string | null>(null)
  const [processMessage, setProcessMessage] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<"documents" | "research">("documents")

  const {
    brief,
    status: briefStatus,
    loading: briefLoading,
    error: briefError,
    generateBrief,
    regenerateBrief,
  } = useResearchBrief(id)

  const handleFilesSelected = useCallback((newFiles: FileEntry[]) => {
    setFiles((prev) => [...prev, ...newFiles])
  }, [])

  const handleRemoveFile = useCallback((id: string) => {
    setFiles((prev) => prev.filter((f) => f.id !== id))
  }, [])

  const handleUploadMore = useCallback(async () => {
    if (!id || files.length === 0) return
    setUploading(true)
    try {
      await uploadFiles(id, files.map((f) => f.file))
      setFiles([])
      setShowUpload(false)
      refetchDocs()
    } catch (err) {
      console.error("Upload failed", err)
    } finally {
      setUploading(false)
    }
  }, [id, files, uploadFiles, refetchDocs])

  const handleProcess = useCallback(
    async (docId: string) => {
      if (!id) return
      setProcessingDocId(docId)
      setProcessMessage(null)
      try {
        const result = await processDocument(id, docId)
        setProcessMessage(result.message)
        refetchDocs()
      } catch (err) {
        setProcessMessage(
          err instanceof Error ? err.message : "Processing failed"
        )
      } finally {
        setProcessingDocId(null)
      }
    },
    [id, refetchDocs]
  )

  const handleGenerateBrief = useCallback(
    (query: string) => {
      void generateBrief(query)
    },
    [generateBrief]
  )

  const handleRegenerate = useCallback(
    (query?: string) => {
      void regenerateBrief(query)
    },
    [regenerateBrief]
  )

  if (matterLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (matterError || !matter || !id) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-8">
        <Button
          variant="ghost"
          className="mb-6"
          onClick={() => navigate("/dashboard")}
        >
          <ArrowLeft className="h-4 w-4 mr-2" />
          Back to Dashboard
        </Button>
        <Card>
          <CardContent className="py-12 text-center text-destructive">
            {matterError || "Matter not found"}
          </CardContent>
        </Card>
      </div>
    )
  }

  const processedCount = documents.filter(
    (d) => d.processing_status === "extracted" || d.processing_status === "failed"
  ).length

  const hasExtractedDocs = documents.some(
    (d) => d.processing_status === "extracted"
  )

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <Button
        variant="ghost"
        className="mb-6"
        onClick={() => navigate("/dashboard")}
      >
        <ArrowLeft className="h-4 w-4 mr-2" />
        Back to Dashboard
      </Button>

      {/* Matter Header */}
      <div className="mb-8">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-3xl font-bold">{matter.title}</h1>
              <Badge
                variant={matter.status === "active" ? "success" : "secondary"}
              >
                {matter.status}
              </Badge>
            </div>
            {matter.case_number && (
              <p className="text-muted-foreground mt-1">
                {matter.case_number}
                {matter.jurisdiction && ` · ${matter.jurisdiction}`}
              </p>
            )}
          </div>
          <Button onClick={() => navigate(`/matters/${id}/timeline`)}>
            <Eye className="h-4 w-4 mr-2" />
            Timeline
          </Button>
        </div>

        {matter.description && (
          <p className="mt-4 text-muted-foreground">{matter.description}</p>
        )}

        <MatterProgressBar
          total={documents.length}
          processed={processedCount}
        />
      </div>

      {/* Process message */}
      {processMessage && (
        <div className="mb-4 text-sm bg-blue-50 text-blue-800 rounded-md px-4 py-3">
          {processMessage}
        </div>
      )}

      {/* Tabs: Documents + Research */}
      <Tabs
        value={activeTab}
        onValueChange={(value) => setActiveTab(value as "documents" | "research")}
        className="mb-8"
      >
        <TabsList>
          <TabsTrigger value="documents">
            <FileText className="h-4 w-4" />
            Documents
          </TabsTrigger>
          <TabsTrigger
            value="research"
            disabled={!hasExtractedDocs}
            title={
              !hasExtractedDocs
                ? "Process documents first to enable legal research."
                : undefined
            }
          >
            <BookOpen className="h-4 w-4" />
            Research
          </TabsTrigger>
        </TabsList>

        <TabsContent value="documents" forceMount>
          {/* Documents Section */}
          <div className="mb-8">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold">
            Documents ({total})
          </h2>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={refetchDocs}
              disabled={docsLoading}
            >
              <RefreshCw
                className={`h-4 w-4 mr-2 ${
                  docsLoading ? "animate-spin" : ""
                }`}
              />
              Refresh
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowUpload(!showUpload)}
            >
              <Upload className="h-4 w-4 mr-2" />
              Upload More
            </Button>
          </div>
        </div>

        {/* Upload more area */}
        {showUpload && (
          <Card className="mb-6">
            <CardContent className="pt-6">
              <DropZone
                onFilesSelected={handleFilesSelected}
                files={files}
                onRemoveFile={handleRemoveFile}
              />
              {uploads.length > 0 && (
                <div className="mt-4 space-y-2">
                  {uploads.map((u) => (
                    <div
                      key={u.fileName}
                      className="flex items-center justify-between text-sm"
                    >
                      <span className="truncate max-w-[200px]">
                        {u.fileName}
                      </span>
                      <UploadProgressBar
                        progress={u.progress}
                        status={u.status}
                        error={u.error}
                      />
                    </div>
                  ))}
                </div>
              )}
              {files.length > 0 && (
                <div className="flex justify-end mt-4">
                  <Button
                    onClick={handleUploadMore}
                    disabled={uploading}
                  >
                    {uploading && (
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    )}
                    Upload {files.length} file(s)
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* Document list */}
        {docsLoading ? (
          <div className="text-center py-8 text-muted-foreground">
            Loading documents...
          </div>
        ) : documents.length === 0 ? (
          <Card>
            <CardContent className="py-12 text-center">
              <FileText className="mx-auto h-10 w-10 text-muted-foreground mb-3" />
              <p className="text-muted-foreground">
                No documents yet. Upload files to start building the timeline.
              </p>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-2">
            {documents.map((doc) => (
              <Card key={doc.id} className="hover:shadow-sm transition-shadow">
                <CardContent className="py-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3 min-w-0">
                      <FileText className="h-5 w-5 shrink-0 text-muted-foreground" />
                      <div className="min-w-0">
                        <p className="text-sm font-medium truncate">
                          {doc.filename}
                        </p>
                        <div className="flex items-center gap-2 text-xs text-muted-foreground mt-0.5">
                          <span className="capitalize">
                            {doc.original_type}
                          </span>
                          {doc.doc_type && (
                            <>
                              <span>·</span>
                              <span>
                                {DOC_TYPE_LABELS[doc.doc_type] || doc.doc_type}
                              </span>
                            </>
                          )}
                          {doc.page_count && (
                            <>
                              <span>·</span>
                              <span>{doc.page_count} page(s)</span>
                            </>
                          )}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <ProcessingBadge status={doc.processing_status} />
                      {doc.processing_status === "pending" && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleProcess(doc.id)}
                          disabled={processingDocId === doc.id}
                        >
                          {processingDocId === doc.id ? (
                            <Loader2 className="h-3 w-3 animate-spin" />
                          ) : (
                            <Clock className="h-3 w-3 mr-1" />
                          )}
                          Process
                        </Button>
                      )}
                    </div>
                  </div>
                  {doc.processing_error && (
                    <p className="mt-1 text-xs text-destructive ml-8">
                      Error: {doc.processing_error}
                    </p>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        )}
          </div>
        </TabsContent>

        <TabsContent value="research" forceMount>
          {hasExtractedDocs ? (
            <div className="space-y-6" data-testid="research-tab-content">
              <ResearchSearch
                matterId={id}
                onGenerateBrief={handleGenerateBrief}
              />
              <ResearchBrief
                matterId={id}
                brief={brief}
                status={briefStatus}
                loading={briefLoading}
                error={briefError}
                onRegenerate={handleRegenerate}
              />
            </div>
          ) : (
            <Card>
              <CardContent className="py-10 text-center text-sm text-muted-foreground">
                Process documents first to enable legal research.
              </CardContent>
            </Card>
          )}
        </TabsContent>
      </Tabs>

      {/* Email Forwarding */}
      {matter.email_address && (
        <EmailForwardingSetup emailAddress={matter.email_address} />
      )}
    </div>
  )
}
