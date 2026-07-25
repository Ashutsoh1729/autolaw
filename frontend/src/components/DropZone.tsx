import { useState, useCallback, useRef } from "react"
import { Upload, File, X } from "lucide-react"
import { cn } from "@/lib/utils"

const ALLOWED_EXTENSIONS = [".pdf", ".txt", ".eml", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"]
const MAX_FILE_SIZE_MB = 50

export interface FileEntry {
  file: File
  id: string
}

interface DropZoneProps {
  onFilesSelected: (files: FileEntry[]) => void
  files: FileEntry[]
  onRemoveFile: (id: string) => void
  maxFiles?: number
}

export function DropZone({ onFilesSelected, files, onRemoveFile, maxFiles = 50 }: DropZoneProps) {
  const [isDragging, setIsDragging] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const validateFiles = useCallback(
    (incoming: File[]): FileEntry[] => {
      setError(null)
      const valid: FileEntry[] = []

      for (const file of incoming) {
        const ext = "." + file.name.split(".").pop()?.toLowerCase()
        if (!ALLOWED_EXTENSIONS.includes(ext as any)) {
          setError(`"${file.name}" has an unsupported file type. Allowed: ${ALLOWED_EXTENSIONS.join(", ")}`)
          continue
        }

        if (file.size > MAX_FILE_SIZE_MB * 1024 * 1024) {
          setError(`"${file.name}" exceeds the ${MAX_FILE_SIZE_MB} MB limit`)
          continue
        }

        if (files.length + valid.length >= maxFiles) {
          setError(`Maximum ${maxFiles} files allowed`)
          break
        }

        valid.push({ file, id: `${file.name}-${Date.now()}-${Math.random()}` })
      }

      return valid
    },
    [files.length, maxFiles]
  )

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setIsDragging(false)
      const droppedFiles = Array.from(e.dataTransfer.files)
      const valid = validateFiles(droppedFiles)
      if (valid.length > 0) onFilesSelected(valid)
    },
    [onFilesSelected, validateFiles]
  )

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }, [])

  const handleDragLeave = useCallback(() => {
    setIsDragging(false)
  }, [])

  const handleBrowse = useCallback(() => {
    inputRef.current?.click()
  }, [])

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      if (e.target.files) {
        const selected = Array.from(e.target.files)
        const valid = validateFiles(selected)
        if (valid.length > 0) onFilesSelected(valid)
        e.target.value = ""
      }
    },
    [onFilesSelected, validateFiles]
  )

  const formatSize = (bytes: number) => {
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  return (
    <div className="space-y-3">
      <div
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={handleBrowse}
        className={cn(
          "border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors",
          isDragging
            ? "border-primary bg-primary/5"
            : "border-gray-300 hover:border-primary/50 hover:bg-gray-50"
        )}
      >
        <Upload className="mx-auto h-10 w-10 text-muted-foreground mb-3" />
        <p className="text-sm font-medium mb-1">
          Drag & drop files here, or click to browse
        </p>
        <p className="text-xs text-muted-foreground">
          Supported: PDF, TXT, EML, PNG, JPG, TIFF (max {MAX_FILE_SIZE_MB} MB each)
        </p>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".pdf,.txt,.eml,.png,.jpg,.jpeg,.tiff,.tif,.bmp"
          className="hidden"
          onChange={handleInputChange}
        />
      </div>

      {error && (
        <p className="text-sm text-red-600 bg-red-50 rounded-md px-3 py-2">{error}</p>
      )}

      {files.length > 0 && (
        <div className="space-y-2">
          <p className="text-sm font-medium">{files.length} file(s) selected</p>
          {files.map((entry) => (
            <div
              key={entry.id}
              className="flex items-center justify-between bg-gray-50 rounded-md px-3 py-2 text-sm"
            >
              <div className="flex items-center gap-2 min-w-0">
                <File className="h-4 w-4 shrink-0 text-muted-foreground" />
                <span className="truncate">{entry.file.name}</span>
                <span className="text-xs text-muted-foreground shrink-0">
                  ({formatSize(entry.file.size)})
                </span>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  onRemoveFile(entry.id)
                }}
                className="text-muted-foreground hover:text-destructive shrink-0 ml-2"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
