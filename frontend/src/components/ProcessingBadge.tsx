import { Badge } from "@/components/ui/badge"

const STATUS_CONFIG: Record<string, { label: string; variant: "info" | "warning" | "success" | "destructive" | "secondary" | "outline" }> = {
  pending: { label: "Pending", variant: "outline" },
  uploading: { label: "Uploading", variant: "info" },
  ocr_pending: { label: "OCR", variant: "info" },
  ocr_done: { label: "OCR Done", variant: "info" },
  classifying: { label: "Classifying", variant: "info" },
  classified: { label: "Classified", variant: "info" },
  extracting: { label: "Extracting", variant: "warning" },
  extracted: { label: "Done", variant: "success" },
  failed: { label: "Failed", variant: "destructive" },
}

interface ProcessingBadgeProps {
  status: string
}

export function ProcessingBadge({ status }: ProcessingBadgeProps) {
  const config = STATUS_CONFIG[status] || { label: status, variant: "secondary" as const }
  return <Badge variant={config.variant}>{config.label}</Badge>
}
