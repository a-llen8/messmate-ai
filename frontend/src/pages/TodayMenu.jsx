import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, Coffee, Sun, Moon, Star, UtensilsCrossed, Check, Lock } from 'lucide-react'
import api from '../api/axios'

const SLOT_META = {
  breakfast: { label: 'Breakfast', icon: Coffee },
  lunch:     { label: 'Lunch',     icon: Sun },
  dinner:    { label: 'Dinner',    icon: Moon },
}

const PLAN_SLOTS = {
  full:             ['breakfast', 'lunch', 'dinner'],
  breakfast_only:   ['breakfast'],
  lunch_only:       ['lunch'],
  dinner_only:      ['dinner'],
  breakfast_lunch:  ['breakfast', 'lunch'],
  breakfast_dinner: ['breakfast', 'dinner'],
  lunch_dinner:     ['lunch', 'dinner'],
}

function StarRating({ value, locked, onChange }) {
  const [hover, setHover] = useState(0)

  return (
    <div className="flex items-center gap-1">
      {[1, 2, 3, 4, 5].map((star) => (
        <button
          key={star}
          type="button"
          disabled={locked}
          onClick={() => onChange(star)}
          onMouseEnter={() => !locked && setHover(star)}
          onMouseLeave={() => !locked && setHover(0)}
          className={`p-0.5 ${locked ? 'cursor-default' : 'cursor-pointer'}`}
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
  const [pending, setPending] = useState({})
  const [locked, setLocked] = useState({})
  const [submitting, setSubmitting] = useState(null)
  const [message, setMessage] = useState('')
  const [allowedSlots, setAllowedSlots] = useState([])

  useEffect(() => {
    fetchSubscription()
    fetchMenu()
  }, [])

  const fetchSubscription = async () => {
    try {
      const res = await api.get('/student/subscription')
      const plan = res.data?.plan_type
      const status = res.data?.status
      if (plan && status === 'active') {
        setAllowedSlots(PLAN_SLOTS[plan] || [])
      }
    } catch (err) {
      console.error(err)
    }
  }

  const fetchMenu = async () => {
    try {
      const res = await api.get('/student/menu/today')
      setMenu(res.data)
      if (Array.isArray(res.data)) {
        const seededPending = {}
        const seededLocked = {}
        res.data.forEach((m) => {
          if (m.my_rating) {
            seededPending[m.id] = m.my_rating
            seededLocked[m.id] = true
          }
        })
        setPending(seededPending)
        setLocked(seededLocked)
      }
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const handlePick = (menuId, score) => {
    setPending((prev) => ({ ...prev, [menuId]: score }))
  }

  const handleSubmit = async (menuId) => {
    const score = pending[menuId]
    if (!score) return
    setMessage('')
    setSubmitting(menuId)
    try {
      await api.post('/student/rating', { menu_id: menuId, score })
      setLocked((prev) => ({ ...prev, [menuId]: true }))
      setMessage('Thanks for rating!')
    } catch (err) {
      setMessage(err.response?.data?.detail || 'Rating failed')
    } finally {
      setSubmitting(null)
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
            const isLocked = !!locked[m.id]
            const value = pending[m.id] || 0
            const inPlan = allowedSlots.includes(m.slot)
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
                  {!inPlan ? (
                    <>
                      <span className="text-xs text-ink/40 flex items-center gap-1">
                        <Lock className="w-3 h-3" />
                        Not included in your plan
                      </span>
                      <StarRating value={0} locked={true} onChange={() => {}} />
                    </>
                  ) : (
                    <>
                      <span className="text-xs text-ink/50">
                        {isLocked ? 'Your rating' : 'Rate this meal'}
                      </span>
                      <div className="flex items-center gap-3">
                        <StarRating value={value} locked={isLocked} onChange={(s) => handlePick(m.id, s)} />
                        {!isLocked && (
                          <button
                            type="button"
                            disabled={!value || submitting === m.id}
                            onClick={() => handleSubmit(m.id)}
                            className="inline-flex items-center gap-1 text-xs font-medium text-white bg-emerald hover:bg-emerald-dark disabled:opacity-40 px-3 py-1.5 rounded-lg transition"
                          >
                            {submitting === m.id ? 'Submitting…' : 'Submit'}
                          </button>
                        )}
                        {isLocked && (
                          <Check className="w-4 h-4 text-emerald-dark" />
                        )}
                      </div>
                    </>
                  )}
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