import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { LogOut, User, CalendarRange, UtensilsCrossed, MessageSquare, Ticket, QrCode } from 'lucide-react'
import api from '../api/axios'

function StatusPill({ status }) {
  const styles = {
    active: 'bg-emerald/15 text-emerald-dark',
    pending: 'bg-amber/15 text-amber',
    cancelled: 'bg-red/15 text-red',
  }
  return (
    <span className={`inline-block px-2.5 py-1 rounded-full text-xs font-semibold uppercase tracking-wide ${styles[status] || 'bg-ink/10 text-ink/60'}`}>
      {status}
    </span>
  )
}

function Dashboard() {
  const [profile, setProfile] = useState(null)
  const [subscription, setSubscription] = useState(null)
  const [menu, setMenu] = useState(null)
  const navigate = useNavigate()

  useEffect(() => {
    fetchData()
  }, [])

  const fetchData = async () => {
    try {
      const [profileRes, subRes, menuRes] = await Promise.all([
        api.get('/student/profile'),
        api.get('/student/subscription'),
        api.get('/student/menu/today'),
      ])
      setProfile(profileRes.data)
      setSubscription(subRes.data)
      setMenu(menuRes.data)
    } catch (err) {
      console.error(err)
    }
  }

  const handleLogout = () => {
    localStorage.removeItem('token')
    localStorage.removeItem('role')
    navigate('/login')
  }

  const navItems = [
    { to: '/profile', icon: User, label: 'Profile' },
    { to: '/subscription', icon: CalendarRange, label: 'Subscription' },
    { to: '/menu', icon: UtensilsCrossed, label: "Today's menu" },
    { to: '/attendance', icon: QrCode, label: 'Give attendance' },
    { to: '/complaints', icon: MessageSquare, label: 'Complaints' },
  ]

  return (
    <div className="min-h-screen bg-cream pb-16">
      <header className="flex items-center justify-between px-6 pt-8 pb-4">
        <div>
          <p className="text-ink/50 text-sm">Welcome back</p>
          <h1 className="font-display text-2xl font-semibold text-ink">
            {profile?.name || '…'}
          </h1>
        </div>
        <button
          onClick={handleLogout}
          className="flex items-center gap-1.5 text-sm text-ink/50 hover:text-red transition"
        >
          <LogOut className="w-4 h-4" />
          Logout
        </button>
      </header>

      <main className="px-6 space-y-6">
        {/* Mess card — signature element */}
        <div className="relative rounded-2xl bg-teal-800 text-cream overflow-hidden shadow-lg">
          <div className="p-5 pb-4">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-2 text-cream/70 text-xs uppercase tracking-widest">
                <Ticket className="w-3.5 h-3.5" />
                Mess card
              </div>
              {subscription?.status && <StatusPill status={subscription.status} />}
            </div>

            {subscription?.status && subscription.status !== 'no subscription' ? (
              <>
                <p className="font-display text-xl font-semibold mt-3 capitalize">
                  {subscription.plan_type?.replace(/_/g, ' ')} plan
                </p>
                <div className="flex items-end justify-between mt-4">
                  <div>
                    <p className="text-cream/60 text-xs">Valid</p>
                    <p className="text-sm">
                      {subscription.start_date} → {subscription.end_date || '—'}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-cream/60 text-xs">Locked price</p>
                    <p className="font-display text-2xl font-semibold">₹{subscription.locked_price}</p>
                  </div>
                </div>
              </>
            ) : (
              <div className="mt-3">
                <p className="text-cream/90">No active subscription yet.</p>
                <Link
                  to="/subscription"
                  className="inline-block mt-3 text-sm font-medium bg-emerald text-white px-4 py-2 rounded-lg hover:bg-emerald-dark transition"
                >
                  Get a mess card →
                </Link>
              </div>
            )}
          </div>

          {/* perforated stub divider */}
          <div className="relative h-0 border-t-2 border-dashed border-cream/25">
            <div className="absolute -left-2.5 -top-2.5 w-5 h-5 rounded-full bg-cream" />
            <div className="absolute -right-2.5 -top-2.5 w-5 h-5 rounded-full bg-cream" />
          </div>

          <div className="px-5 py-3 flex items-center justify-between text-xs text-cream/60">
            <span>MessMate</span>
            <span>{profile?.email}</span>
          </div>
        </div>

        {/* Today's menu preview */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <h2 className="font-display text-lg font-semibold text-ink">Today on the board</h2>
            <Link to="/menu" className="text-sm text-teal-700 font-medium hover:underline">
              See all →
            </Link>
          </div>
          <div className="bg-white rounded-2xl shadow-sm border border-ink/5 divide-y divide-ink/5">
            {Array.isArray(menu) && menu.length > 0 ? (
              menu.map((m, i) => (
                <div key={i} className="px-4 py-3 flex items-center justify-between">
                  <span className="capitalize text-sm font-medium text-ink/80">{m.slot}</span>
                  <span className="text-sm text-ink/60">{m.items}</span>
                </div>
              ))
            ) : (
              <p className="px-4 py-6 text-center text-sm text-ink/50">
                Nothing posted yet — check back soon.
              </p>
            )}
          </div>
        </div>

        {/* Quick nav */}
        <div className="grid grid-cols-4 gap-3">
          {navItems.map(({ to, icon: Icon, label }) => (
            <Link
              key={to}
              to={to}
              className="flex flex-col items-center gap-2 bg-white rounded-xl py-4 shadow-sm border border-ink/5 hover:border-emerald/40 transition"
            >
              <Icon className="w-5 h-5 text-teal-700" />
              <span className="text-xs text-ink/70 text-center leading-tight">{label}</span>
            </Link>
          ))}
        </div>
      </main>
    </div>
  )
}

export default Dashboard