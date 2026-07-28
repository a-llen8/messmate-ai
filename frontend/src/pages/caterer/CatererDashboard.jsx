import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Users, CalendarCheck, UtensilsCrossed,
  MessageSquare, ClipboardList, ArrowRight,
} from 'lucide-react'
import api from '../../api/axios'
import CatererLayout from '../../components/CatererLayout'

function StatCard({ label, value, icon: Icon }) {
  return (
    <div className="bg-white rounded-xl border border-ink/10 p-5">
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs font-medium text-ink/50 uppercase tracking-wide">{label}</span>
        <Icon className="w-4 h-4 text-ink/30" />
      </div>
      <p className="font-display text-3xl font-semibold text-ink">{value}</p>
    </div>
  )
}

function CatererDashboard() {
  const [stats, setStats] = useState(null)

  useEffect(() => {
    fetchStats()
  }, [])

  const fetchStats = async () => {
    try {
      const res = await api.get('/caterer/dashboard')
      setStats(res.data)
    } catch (err) {
      console.error(err)
    }
  }

  const quickLinks = [
    { to: '/caterer/menu', label: "Update today's menu", icon: UtensilsCrossed },
    { to: '/caterer/requests', label: 'Review subscription requests', icon: ClipboardList },
    { to: '/caterer/complaints', label: 'Check open complaints', icon: MessageSquare },
  ]

  return (
    <CatererLayout title="Dashboard" subtitle="Everything happening in your mess, today.">
      {!stats ? (
        <div className="animate-pulse text-ink/40 text-sm">Loading…</div>
      ) : (
        <>
          <div className="grid grid-cols-3 gap-4 mb-8">
            <StatCard label="Active students" value={stats.total_students} icon={Users} />
            <StatCard label="Active subscriptions" value={stats.active_subs} icon={CalendarCheck} />
            <StatCard label="Today's attendance" value={stats.today_attendance} icon={UtensilsCrossed} />
          </div>

          <div className="grid grid-cols-2 gap-4 mb-8">
            <div className="bg-white rounded-xl border border-ink/10 p-5 flex items-center justify-between">
              <div>
                <p className="text-xs font-medium text-ink/50 uppercase tracking-wide mb-1">Open complaints</p>
                <p className="font-display text-2xl font-semibold text-ink">{stats.open_complaints}</p>
              </div>
              {stats.open_complaints > 0 && (
                <span className="w-2.5 h-2.5 rounded-full bg-red" />
              )}
            </div>
            <div className="bg-white rounded-xl border border-ink/10 p-5 flex items-center justify-between">
              <div>
                <p className="text-xs font-medium text-ink/50 uppercase tracking-wide mb-1">Pending requests</p>
                <p className="font-display text-2xl font-semibold text-ink">{stats.pending_requests}</p>
              </div>
              {stats.pending_requests > 0 && (
                <span className="w-2.5 h-2.5 rounded-full bg-amber" />
              )}
            </div>
          </div>

          <p className="text-xs font-medium text-ink/50 uppercase tracking-wide mb-3">Quick actions</p>
          <div className="bg-white rounded-xl border border-ink/10 divide-y divide-ink/5">
            {quickLinks.map(({ to, label, icon: Icon }) => (
              <Link
                key={to}
                to={to}
                className="flex items-center justify-between px-5 py-4 hover:bg-ink/[0.02] transition group"
              >
                <div className="flex items-center gap-3">
                  <Icon className="w-4 h-4 text-teal-700" />
                  <span className="text-sm font-medium text-ink">{label}</span>
                </div>
                <ArrowRight className="w-4 h-4 text-ink/20 group-hover:text-ink/50 transition" />
              </Link>
            ))}
          </div>
        </>
      )}
    </CatererLayout>
  )
}

export default CatererDashboard