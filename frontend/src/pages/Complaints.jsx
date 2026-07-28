import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, Utensils, Sparkles, Users, MoreHorizontal, Send } from 'lucide-react'
import api from '../api/axios'

const CATEGORIES = [
  { key: 'food_quality', label: 'Food quality', icon: Utensils },
  { key: 'hygiene',      label: 'Hygiene',      icon: Sparkles },
  { key: 'service',      label: 'Service',      icon: Users },
  { key: 'other',        label: 'Other',        icon: MoreHorizontal },
]

function Complaints() {
  const [text, setText] = useState('')
  const [category, setCategory] = useState('food_quality')
  const [message, setMessage] = useState('')
  const [isError, setIsError] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setMessage('')
    setSubmitting(true)
    try {
      await api.post('/student/complaint', { text, category })
      setMessage('Complaint submitted — your caterer has been notified.')
      setIsError(false)
      setText('')
    } catch (err) {
      setMessage(err.response?.data?.detail || 'Submission failed')
      setIsError(true)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen bg-cream pb-16">
      <header className="px-6 pt-8 pb-4">
        <Link to="/" className="inline-flex items-center gap-1.5 text-sm text-ink/50 hover:text-ink mb-4">
          <ArrowLeft className="w-4 h-4" />
          Back
        </Link>
        <h1 className="font-display text-2xl font-semibold text-ink">Raise a complaint</h1>
        <p className="text-ink/50 text-sm mt-1">Let your caterer know what needs fixing.</p>
      </header>

      <main className="px-6">
        <form onSubmit={handleSubmit} className="space-y-6">
          <div>
            <label className="block text-sm font-medium text-ink/70 mb-2">Category</label>
            <div className="grid grid-cols-2 gap-3">
              {CATEGORIES.map(({ key, label, icon: Icon }) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setCategory(key)}
                  className={`text-left p-4 rounded-xl border-2 transition ${
                    category === key
                      ? 'border-emerald bg-emerald/5'
                      : 'border-ink/10 bg-white hover:border-ink/20'
                  }`}
                >
                  <Icon className={`w-5 h-5 mb-2 ${category === key ? 'text-emerald-dark' : 'text-ink/40'}`} />
                  <p className="text-sm font-semibold text-ink">{label}</p>
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-ink/70 mb-1.5">Details</label>
            <textarea
              placeholder="Describe your complaint…"
              value={text}
              onChange={(e) => setText(e.target.value)}
              required
              rows={5}
              className="w-full px-4 py-3 rounded-xl border border-ink/10 bg-white text-ink placeholder:text-ink/30 focus:outline-none focus:ring-2 focus:ring-emerald transition resize-none"
            />
          </div>

          {message && (
            <div
              className={`text-sm rounded-lg px-3 py-2 ${
                isError ? 'text-red bg-red/10' : 'text-emerald-dark bg-emerald/10'
              }`}
            >
              {message}
            </div>
          )}

          <button
            type="submit"
            disabled={submitting || !text.trim()}
            className="w-full flex items-center justify-center gap-2 bg-emerald hover:bg-emerald-dark disabled:opacity-40 disabled:cursor-not-allowed text-white font-medium py-3.5 rounded-xl transition"
          >
            <Send className="w-4 h-4" />
            {submitting ? 'Submitting…' : 'Submit complaint'}
          </button>
        </form>
      </main>
    </div>
  )
}

export default Complaints