import { Copy, Mail } from "lucide-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"

interface EmailForwardingSetupProps {
  emailAddress: string
}

export function EmailForwardingSetup({ emailAddress }: EmailForwardingSetupProps) {
  const copyToClipboard = () => {
    navigator.clipboard.writeText(emailAddress)
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg flex items-center gap-2">
          <Mail className="h-5 w-5" />
          Email Ingestion
        </CardTitle>
        <CardDescription>
          Forward case-related emails to this address, and they will be
          automatically attached to this matter.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-center gap-2">
          <code className="flex-1 bg-muted px-3 py-2 rounded-md text-sm font-mono break-all">
            {emailAddress}
          </code>
          <Button variant="outline" size="sm" onClick={copyToClipboard}>
            <Copy className="h-4 w-4" />
          </Button>
        </div>
        <div className="text-xs text-muted-foreground space-y-1">
          <p><strong>How to use:</strong></p>
          <ol className="list-decimal list-inside space-y-0.5">
            <li>Forward relevant emails to this address</li>
            <li>Emails are automatically parsed and linked to this matter</li>
            <li>Attachments are extracted and queued for processing</li>
          </ol>
        </div>
      </CardContent>
    </Card>
  )
}
