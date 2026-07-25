import { Link, useLocation } from "react-router-dom"
import { Scale } from "lucide-react"

export function Navbar() {
  const location = useLocation()

  return (
    <header className="border-b bg-white">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-14">
          <div className="flex items-center gap-6">
            <Link to="/dashboard" className="flex items-center gap-2 font-bold text-lg">
              <Scale className="h-6 w-6 text-primary" />
              <span>AutoLaw</span>
            </Link>
            <nav className="flex items-center gap-1 text-sm text-muted-foreground">
              <Link
                to="/dashboard"
                className={`px-3 py-1.5 rounded-md transition-colors ${
                  location.pathname === "/dashboard"
                    ? "bg-primary/10 text-primary font-medium"
                    : "hover:bg-muted"
                }`}
              >
                Dashboard
              </Link>
            </nav>
          </div>
        </div>
      </div>
    </header>
  )
}
