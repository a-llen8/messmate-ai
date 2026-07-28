import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, Coffee, Sun, Moon, Star, UtensilsCrossed } from 'lucide-react'
import api from '../api/axios'

const SLOT_META = {
  breakfast: { label: 'Breakfast', icon: Coffee },
  lunch:     { label: 'Lunch',     icon: Sun },
  dinner:    { label: 'Dinner',    icon: Moon },
}

function StarRating({ menuId, value, onRate }) {
  const [hover, setHover] = useState(0)

  return (
    <div className="flex items-center gap-1">
      {[1, 2, 3, 4, 5].map((star) => (
        <button
          key={star}
          type="button"
          onClick={() => onRate(menuId, star)}
          onMouseEnter={() => setHover(star)}
          onMouseLeave={() => setHover(0)}
          className="p-0.5"
        >
          <Star
            className={`w-5 h-5 transition ${
              star <= (hover || value)
                ? 'fill-amber text-amber'
                : 'text-ink/20'
            }`}
          />
        </button>
      ))}
    </div>
  )
}

function TodayMenu() {
  const [menu, setMenu] = useState(null)
  const [loading, setLoading] = useState(true)
  const [ratings, setRatings] = useState({})
  const [message, setMessage] = useState('')

  useEffect(() => {
    fetchMenu()
  }, [])

  const fetchMenu = async () => {
    try {
      const res = await api.get('/student/menu/today')
      setMenu(res.data)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const handleRate = async (menuId, score) => {
    setMessage('')
    setRatings((prev) => ({ ...prev, [menuId]: score }))
    try {
      await api.post('/student/rating', { menu_id: menuId, score })
      setMessage('Thanks for rating!')
    } catch (err) {
      setMessage(err.response?.data?.detail || 'Rating failed')
    }
  }

  const items = Array.isArray(menu) ? menu : []

  return (
    <div className="min-h-screen bg-cream pb-16">
      <header className="px-6 pt-8 pb-4">
        <Link to="/" className="inline-flex items-center gap-1.5 text-sm text-ink/50 hover:text-ink mb-4">
          <ArrowLeft className="w-4 h-4" />
          Back
        </Link>
        <h1 className="font-display text-2xl font-semibold text-ink">Today's menu</h1>
        <p className="text-ink/50 text-sm mt-1">What's on the board right now.</p>
      </header>

      <main className="px-6 space-y-4">
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <div className="animate-pulse text-ink/40 text-sm">Loading…</div>
          </div>
        ) : items.length === 0 ? (
          <div className="bg-white rounded-2xl shadow-sm border border-ink/5 py-12 px-6 text-center">
            <UtensilsCrossed className="w-8 h-8 text-ink/20 mx-auto mb-3" />
            <p className="text-sm text-ink/50">Nothing posted yet — check back soon.</p>
          </div>
        ) : (
          items.map((m, i) => {
            const meta = SLOT_META[m.slot] || { label: m.slot, icon: UtensilsCrossed }
            const Icon = meta.icon
            return (
              <div key={i} className="bg-white rounded-2xl shadow-sm border border-ink/5 p-5">
                <div className="flex items-center gap-2 mb-2">
                  <div className="w-8 h-8 rounded-full bg-teal-800/10 flex items-center justify-center">
                    <Icon className="w-4 h-4 text-teal-700" />
                  </div>
                  <h2 className="font-display text-lg font-semibold text-ink capitalize">{meta.label}</h2>
                </div>
                <p className="text-sm text-ink/70 mb-4 pl-10">{m.items}</p>
                <div className="pl-10 flex items-center justify-between">
                  <span className="text-xs text-ink/50">Rate this meal</span>
                  <StarRating menuId={m.id} value={ratings[m.id] || 0} onRate={handleRate} />
                </div>
              </div>
            )
          })
        )}

        {message && (
          <div className="text-sm text-emerald-dark bg-emerald/10 rounded-lg px-3 py-2 text-center">
            {message}
          </div>
        )}
      </main>
    </div>
  )
}

export default TodayMenu