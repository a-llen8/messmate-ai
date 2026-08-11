import { Link, useNavigate, useLocation } from 'react-router-dom'
import {
  LayoutDashboard, UtensilsCrossed, ClipboardList,
  MessageSquare, ScanLine, Wallet, LogOut, Star, Sparkles,
} from 'lucide-react'

const NAV_ITEMS = [
  { to: '/caterer',            label: 'Dashboard',  icon: LayoutDashboard },
  { to: '/caterer/recommendations', label: 'Recommendations', icon: Sparkles },
  { to: '/caterer/menu',       label: 'Menu',        icon: UtensilsCrossed },
  { to: '/caterer/requests',   label: 'Requests',    icon: ClipboardList },
  { to: '/caterer/complaints', label: 'Complaints',  icon: MessageSquare },
  { to: '/caterer/ratings',    label: 'Ratings',     icon: Star },
  { to: '/caterer/pricing',    label: 'Pricing',     icon: Wallet },
  { to: '/caterer/scan',       label: 'Scan',        icon: ScanLine },
]

function CatererLayout({ title, subtitle, children }) {
  const navigate = useNavigate()
  const location = useLocation()

  const handleLogout = () => {
    localStorage.removeItem('token')
    localStorage.removeItem('role')
    navigate('/login')
  }

  return (
    <div className="min-h-screen bg-cream-dim flex">
      {/* Sidebar */}
      <aside className="w-56 shrink-0 bg-white border-r border-ink/10 flex flex-col">
        <div className="px-5 py-6">
          <p className="font-display text-lg font-semibold text-ink">MessMate</p>
          <p className="text-xs text-ink/40 mt-0.5">Caterer console</p>
        </div>

        <nav className="flex-1 px-3 space-y-0.5">
          {NAV_ITEMS.map(({ to, label, icon: Icon }) => {
            const active = location.pathname === to
            return (
              <Link
                key={to}
                to={to}
                className={`flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium transition ${
                  active
                    ? 'bg-teal-800 text-cream'
                    : 'text-ink/60 hover:bg-ink/5 hover:text-ink'
                }`}
              >
                <Icon className="w-4 h-4" />
                {label}
              </Link>
            )
          })}
        </nav>

        <div className="px-3 pb-5">
          <button
            onClick={handleLogout}
            className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium text-ink/50 hover:bg-red/10 hover:text-red transition"
          >
            <LogOut className="w-4 h-4" />
            Logout
          </button>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex-1 min-w-0">
        <header className="bg-white border-b border-ink/10 px-8 py-5">
          <h1 className="font-display text-xl font-semibold text-ink">{title}</h1>
          {subtitle && <p className="text-sm text-ink/50 mt-0.5">{subtitle}</p>}
        </header>
        <main className="p-8 max-w-4xl">{children}</main>
      </div>
    </div>
  )
}

export default CatererLayout