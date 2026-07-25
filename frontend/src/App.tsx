import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom"
import { Navbar } from "@/components/Navbar"
import { Dashboard } from "@/pages/Dashboard"
import { CreateMatter } from "@/pages/CreateMatter"
import { MatterDetail } from "@/pages/MatterDetail"
import { TimelineView } from "@/pages/TimelineView"

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-background">
        <Navbar />
        <main>
          <Routes>
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/matters/new" element={<CreateMatter />} />
            <Route path="/matters/:id" element={<MatterDetail />} />
            <Route path="/matters/:id/timeline" element={<TimelineView />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
