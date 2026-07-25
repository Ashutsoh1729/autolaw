import { useState, useCallback } from "react"
import { useNavigate } from "react-router-dom"
import { ArrowLeft, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { DropZone, type FileEntry } from "@/components/DropZone"
import { UploadProgressBar } from "@/components/ProgressBar"
import { useUpload } from "@/hooks/useUpload"
import { createMatter } from "@/hooks/useMatter"

const CASE_TYPES = [
  "Civil",
  "Criminal",
  "Family",
  "Corporate",
  "Real Estate",
  "Employment",
  "Intellectual Property",
  "Personal Injury",
  "Immigration",
  "Other",
]

interface FormData {
  title: string
  case_number: string
  case_type: string
  jurisdiction: string
  description: string
}

interface FormErrors {
  title?: string
  case_number?: string
}

export function CreateMatter() {
  const navigate = useNavigate()
  const { uploads, uploadFiles } = useUpload()

  const [formData, setFormData] = useState<FormData>({
    title: "",
    case_number: "",
    case_type: "",
    jurisdiction: "",
    description: "",
  })
  const [errors, setErrors] = useState<FormErrors>({})
  const [files, setFiles] = useState<FileEntry[]>([])
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  const handleFieldChange = useCallback(
    (field: keyof FormData, value: string) => {
      setFormData((prev) => ({ ...prev, [field]: value }))
      // Clear field error on change
      if (errors[field as keyof FormErrors]) {
        setErrors((prev) => ({ ...prev, [field]: undefined }))
      }
    },
    [errors]
  )

  const handleFilesSelected = useCallback(
    (newFiles: FileEntry[]) => {
      setFiles((prev) => [...prev, ...newFiles])
    },
    []
  )

  const handleRemoveFile = useCallback((id: string) => {
    setFiles((prev) => prev.filter((f) => f.id !== id))
  }, [])

  const validate = useCallback((): boolean => {
    const newErrors: FormErrors = {}
    if (!formData.title.trim()) {
      newErrors.title = "Case title is required"
    }
    setErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }, [formData.title])

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault()
      if (!validate()) return

      setSubmitting(true)
      setSubmitError(null)

      try {
        // Create the matter
        const matter = await createMatter({
          title: formData.title.trim(),
          case_number: formData.case_number.trim() || undefined,
          case_type: formData.case_type || undefined,
          jurisdiction: formData.jurisdiction.trim() || undefined,
          description: formData.description.trim() || undefined,
        })

        // Upload files if any
        if (files.length > 0) {
          await uploadFiles(matter.id, files.map((f) => f.file))
        }

        // Navigate to the new matter's detail page
        navigate(`/matters/${matter.id}`)
      } catch (err) {
        setSubmitError(
          err instanceof Error ? err.message : "Failed to create matter"
        )
      } finally {
        setSubmitting(false)
      }
    },
    [formData, files, navigate, validate, uploadFiles]
  )

  return (
    <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <Button
        variant="ghost"
        className="mb-6"
        onClick={() => navigate("/dashboard")}
      >
        <ArrowLeft className="h-4 w-4 mr-2" />
        Back to Dashboard
      </Button>

      <Card>
        <CardHeader>
          <CardTitle className="text-2xl">Create New Matter</CardTitle>
          <CardDescription>
            Enter case details and upload related documents to get started.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-6">
            {/* Case Title (required) */}
            <div className="space-y-2">
              <Label htmlFor="title">
                Case Title <span className="text-destructive">*</span>
              </Label>
              <Input
                id="title"
                placeholder="e.g., Smith v. Corporation"
                value={formData.title}
                onChange={(e) => handleFieldChange("title", e.target.value)}
                className={errors.title ? "border-destructive" : ""}
              />
              {errors.title && (
                <p className="text-sm text-destructive">{errors.title}</p>
              )}
            </div>

            {/* Case Number */}
            <div className="space-y-2">
              <Label htmlFor="case_number">Case Number</Label>
              <Input
                id="case_number"
                placeholder="e.g., 2024-CV-1234"
                value={formData.case_number}
                onChange={(e) =>
                  handleFieldChange("case_number", e.target.value)
                }
              />
            </div>

            {/* Case Type and Jurisdiction */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="case_type">Case Type</Label>
                <Select
                  value={formData.case_type}
                  onValueChange={(v) => handleFieldChange("case_type", v)}
                >
                  <SelectTrigger id="case_type">
                    <SelectValue placeholder="Select type..." />
                  </SelectTrigger>
                  <SelectContent>
                    {CASE_TYPES.map((type) => (
                      <SelectItem key={type} value={type}>
                        {type}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="jurisdiction">Jurisdiction</Label>
                <Input
                  id="jurisdiction"
                  placeholder="e.g., Northern District of California"
                  value={formData.jurisdiction}
                  onChange={(e) =>
                    handleFieldChange("jurisdiction", e.target.value)
                  }
                />
              </div>
            </div>

            {/* Description */}
            <div className="space-y-2">
              <Label htmlFor="description">Description</Label>
              <Textarea
                id="description"
                placeholder="Brief description of the case..."
                rows={3}
                value={formData.description}
                onChange={(e) =>
                  handleFieldChange("description", e.target.value)
                }
              />
            </div>

            {/* File Upload */}
            <div className="space-y-2">
              <Label>Documents</Label>
              <DropZone
                onFilesSelected={handleFilesSelected}
                files={files}
                onRemoveFile={handleRemoveFile}
              />
            </div>

            {/* Upload progress */}
            {uploads.length > 0 && (
              <div className="space-y-2">
                <Label>Upload Progress</Label>
                {uploads.map((u) => (
                  <div
                    key={u.fileName}
                    className="flex items-center justify-between text-sm"
                  >
                    <span className="truncate max-w-[200px]">{u.fileName}</span>
                    <UploadProgressBar
                      progress={u.progress}
                      status={u.status}
                      error={u.error}
                    />
                  </div>
                ))}
              </div>
            )}

            {/* Submit error */}
            {submitError && (
              <div className="text-sm text-destructive bg-destructive/10 rounded-md px-3 py-2">
                {submitError}
              </div>
            )}

            {/* Submit */}
            <div className="flex items-center gap-4 pt-4">
              <Button type="submit" disabled={submitting} size="lg">
                {submitting && (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                )}
                {submitting ? "Creating Matter..." : "Create Matter"}
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={() => navigate("/dashboard")}
              >
                Cancel
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
