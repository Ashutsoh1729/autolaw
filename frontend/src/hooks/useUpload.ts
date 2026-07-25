import { useState, useCallback } from "react"

interface UploadProgress {
  fileName: string
  progress: number
  status: "pending" | "uploading" | "done" | "error"
  error?: string
}

interface UseUploadReturn {
  uploads: UploadProgress[]
  uploadFiles: (matterId: string, files: File[]) => Promise<void>
  clearUploads: () => void
}

export function useUpload(): UseUploadReturn {
  const [uploads, setUploads] = useState<UploadProgress[]>([])

  const updateProgress = useCallback(
    (fileName: string, updates: Partial<UploadProgress>) => {
      setUploads((prev) =>
        prev.map((u) => (u.fileName === fileName ? { ...u, ...updates } : u))
      )
    },
    []
  )

  const uploadFiles = useCallback(
    async (matterId: string, files: File[]) => {
      const newUploads: UploadProgress[] = files.map((f) => ({
        fileName: f.name,
        progress: 0,
        status: "pending" as const,
      }))
      setUploads((prev) => [...prev, ...newUploads])

      for (const file of files) {
        updateProgress(file.name, { status: "uploading", progress: 0 })

        try {
          const formData = new FormData()
          formData.append("files", file)

          const xhr = new XMLHttpRequest()

          await new Promise<void>((resolve, reject) => {
            xhr.upload.addEventListener("progress", (e) => {
              if (e.lengthComputable) {
                const pct = Math.round((e.loaded / e.total) * 100)
                updateProgress(file.name, { progress: pct })
              }
            })

            xhr.addEventListener("load", () => {
              if (xhr.status >= 200 && xhr.status < 300) {
                updateProgress(file.name, { status: "done", progress: 100 })
                resolve()
              } else {
                const msg = `Upload failed: ${xhr.status} ${xhr.statusText}`
                updateProgress(file.name, { status: "error", error: msg })
                reject(new Error(msg))
              }
            })

            xhr.addEventListener("error", () => {
              const msg = "Network error during upload"
              updateProgress(file.name, { status: "error", error: msg })
              reject(new Error(msg))
            })

            xhr.open("POST", `/api/matters/${matterId}/documents`)
            xhr.send(formData)
          })
        } catch (err) {
          updateProgress(file.name, {
            status: "error",
            error: err instanceof Error ? err.message : "Upload failed",
          })
        }
      }
    },
    [updateProgress]
  )

  const clearUploads = useCallback(() => {
    setUploads([])
  }, [])

  return { uploads, uploadFiles, clearUploads }
}
