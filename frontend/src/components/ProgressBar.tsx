import { Progress } from "@/components/ui/progress"

interface UploadProgressBarProps {
  progress: number
  status: "pending" | "uploading" | "done" | "error"
  error?: string
}

export function UploadProgressBar({ progress, status, error }: UploadProgressBarProps) {
  if (status === "done") {
    return (
      <div className="flex items-center gap-2">
        <Progress value={100} className="h-1.5 w-24" />
        <span className="text-xs text-green-600">✓ Done</span>
      </div>
    )
  }

  if (status === "error") {
    return (
      <div className="flex items-center gap-2">
        <Progress value={progress} className="h-1.5 w-24 bg-red-100" />
        <span className="text-xs text-red-600">{error || "Failed"}</span>
      </div>
    )
  }

  return (
    <div className="flex items-center gap-2">
      <Progress value={progress} className="h-1.5 w-24" />
      <span className="text-xs text-muted-foreground">{progress}%</span>
    </div>
  )
}

interface MatterProgressBarProps {
  total: number
  processed: number
}

export function MatterProgressBar({ total, processed }: MatterProgressBarProps) {
  if (total === 0) return null
  const pct = Math.round((processed / total) * 100)

  return (
    <div className="flex items-center gap-2">
      <Progress value={pct} className="h-2 flex-1" />
      <span className="text-xs text-muted-foreground whitespace-nowrap">
        {processed} of {total} documents
      </span>
    </div>
  )
}
