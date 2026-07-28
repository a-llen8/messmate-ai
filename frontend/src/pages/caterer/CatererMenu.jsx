import { useEffect, useState } from 'react'
import { Coffee, Sun, Moon, Plus, UtensilsCrossed } from 'lucide-react'
import api from '../../api/axios'
import CatererLayout from '../../components/CatererLayout'

const SLOT_META = {
  breakfast: { label: 'Breakfast', icon: Coffee },
  lunch:     { label: 'Lunch',     icon: Sun },
  dinner:    { label: 'Dinner',    icon: Moon },
}

function CatererMenu() {
  const [menus, setMenus] = useState([])
  const [loading, setLoading] = useState(true)
  const [date, setDate] = useState('')
  const [slot, setSlot] = useState('breakfast')
  const [items, setItems] = useState('')
  const [message, setMessage] = useState('')
  const [isError, setIsError] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    fetchMenus()
  }, [])

  const fetchMenus = async () => {
    try {
      const res = await api.get('/caterer/menu')
      setMenus(res.data)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setMessage('')
    setSubmitting(true)
    try {
      await api.post('/caterer/menu', { date, slot, items })
      setMessage('Menu added')
      setIsError(false)
      setItems('')
      fetchMenus()
    } catch (err) {
      setMessage(err.response?.data?.detail || 'Failed to create menu')
      setIsError(true)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <CatererLayout title="Menu" subtitle="Post what's being served, per slot.">
      <div className="bg-white rounded-xl border border-ink/10 p-6 mb-8">
        <p className="text-sm font-semibold text-ink mb-4">Add a menu entry</p>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-ink/50 mb-1.5">Date</label>
              <input
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                required
                className="w-full px-3 py-2.5 rounded-lg border border-ink/10 bg-cream-dim text-sm text-ink focus:outline-none focus:ring-2 focus:ring-emerald transition"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-ink/50 mb-1.5">Slot</label>
              <select
                value={slot}
                onChange={(e) => setSlot(e.target.value)}
                className="w-full px-3 py-2.5 rounded-lg border border-ink/10 bg-cream-dim text-sm text-ink focus:outline-none focus:ring-2 focus:ring-emerald transition"
              >
                <option value="breakfast">Breakfast</option>
                <option value="lunch">Lunch</option>
                <option value="dinner">Dinner</option>
              </select>
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-ink/50 mb-1.5">Items</label>
            <input
              type="text"
              placeholder="e.g. Poha, boiled eggs, tea"
              value={items}
              onChange={(e) => setItems(e.target.value)}
              required
              className="w-full px-3 py-2.5 rounded-lg border border-ink/10 bg-cream-dim text-sm text-ink placeholder:text-ink/30 focus:outline-none focus:ring-2 focus:ring-emerald transition"
            />
          </div>

          {message && (
            <div className={`text-sm rounded-lg px-3 py-2 ${isError ? 'text-red bg-red/10' : 'text-emerald-dark bg-emerald/10'}`}>
              {message}
            </div>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="inline-flex items-center gap-2 bg-emerald hover:bg-emerald-dark disabled:opacity-40 text-white text-sm font-medium px-4 py-2.5 rounded-lg transition"
          >
            <Plus className="w-4 h-4" />
            {submitting ? 'Adding…' : 'Add menu'}
          </button>
        </form>
      </div>

      <p className="text-xs font-medium text-ink/50 uppercase tracking-wide mb-3">Posted menus</p>
      <div className="bg-white rounded-xl border border-ink/10 divide-y divide-ink/5">
        {loading ? (
          <div className="p-5 text-sm text-ink/40 animate-pulse">Loading…</div>
        ) : menus.length === 0 ? (
          <div className="p-8 text-center">
            <UtensilsCrossed className="w-6 h-6 text-ink/20 mx-auto mb-2" />
            <p className="text-sm text-ink/50">No menus posted yet.</p>
          </div>
        ) : (
          menus.map((m) => {
            const meta = SLOT_META[m.slot] || { label: m.slot, icon: UtensilsCrossed }
            const Icon = meta.icon
            return (
              <div key={m.id} className="flex items-center gap-4 px-5 py-3.5">
                <div className="w-8 h-8 rounded-full bg-teal-800/10 flex items-center justify-center shrink-0">
                  <Icon className="w-4 h-4 text-teal-700" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-ink">{meta.label} <span className="text-ink/40 font-normal">· {m.date}</span></p>
                  <p className="text-sm text-ink/60 truncate">{m.items}</p>
                </div>
              </div>
            )
          })
        )}
      </div>
    </CatererLayout>
  )
}

export default CatererMenu