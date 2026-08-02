import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Coffee, Sun, Moon, UtensilsCrossed, Ticket, Loader2 } from 'lucide-react'
import api from '../api/axios'

const PLAN_META = {
  full: { label: 'Full plan', desc: 'Breakfast, lunch & dinner', icon: UtensilsCrossed },
  breakfast_only: { label: 'Breakfast only', desc: 'Start your day right', icon: Coffee },
  lunch_only: { label: 'Lunch only', desc: 'Midday meal covered', icon: Sun },
  dinner_only: { label: 'Dinner only', desc: 'Evening meal covered', icon: Moon },
  breakfast_lunch: { label: 'Breakfast + Lunch', desc: 'Two meals a day', icon: Coffee },
  breakfast_dinner: { label: 'Breakfast + Dinner', desc: 'Two meals a day', icon: Coffee },
  lunch_dinner: { label: 'Lunch + Dinner', desc: 'Two meals a day', icon: Sun },
}

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

function Subscription() {
  const [subscription, setSubscription] = useState(null)
  const [planType, setPlanType] = useState('full')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [preview, setPreview] = useState(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewError, setPreviewError] = useState('')
  const [message, setMessage] = useState('')

  useEffect(() => {
    fetchSubscription()
  }, [])

  useEffect(() => {
    if (!startDate || !endDate || !planType) {
      setPreview(null)
      return
    }
    const days = (new Date(endDate) - new Date(startDate)) / 86400000 + 1
    if (days < 7) {
      setPreview(null)
      setPreviewError('Pick a range of at least 7 days')
      return
    }
    setPreviewError('')
    fetchPreview()
  }, [planType, startDate, endDate])

  const fetchSubscription = async () => {
    try {
      const res = await api.get('/student/subscription')
      setSubscription(res.data)
    } catch (err) {
      console.error(err)
    }
  }

  const fetchPreview = async () => {
    setPreviewLoading(true)
    try {
      const res = await api.get('/student/price-preview', {
        params: { plan_type: planType, start_date: startDate, end_date: endDate },
      })
      setPreview(res.data)
      setPreviewError('')
    } catch (err) {
      setPreview(null)
      setPreviewError(err.response?.data?.detail || 'Could not calculate price')
    } finally {
      setPreviewLoading(false)
    }
  }

  const handleRequest = async (e) => {
    e.preventDefault()
    setMessage('')
    try {
      await api.post('/student/subscription/request', {
        plan_type: planType,
        start_date: startDate,
        end_date: endDate,
      })
      setMessage('Request sent — your caterer will confirm it shortly.')
      fetchSubscription()
    } catch (err) {
      setMessage(err.response?.data?.detail || 'Could not submit request')
    }
  }

  const handleCancel = async () => {
    setMessage('')
    try {
      await api.post('/student/subscription/cancel')
      setMessage('Cancellation requested.')
      fetchSubscription()
    } catch (err) {
      setMessage(err.response?.data?.detail || 'Could not cancel')
    }
  }

  const hasActive = subscription && subscription.status === 'active'

  return (
    <div className="min-h-screen bg-cream pb-16">
      <header className="px-6 pt-8 pb-4">
        <h1 className="font-display text-2xl font-semibold text-ink">Subscription</h1>
        <p className="text-ink/50 text-sm mt-1">Your mess card, on your terms.</p>
      </header>

      <main className="px-6 space-y-6">
        {hasActive ? (
          <>
          <div className="relative rounded-2xl bg-teal-800 text-cream overflow-hidden shadow-lg">
            <div className="p-5 pb-4">
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-2 text-cream/70 text-xs uppercase tracking-widest">
                  <Ticket className="w-3.5 h-3.5" />
                  Mess card
                </div>
                <StatusPill status={subscription.status} />
              </div>
              <p className="font-display text-xl font-semibold mt-3 capitalize">
                {subscription.plan_type?.replace(/_/g, ' ')} plan
              </p>
              <div className="flex items-end justify-between mt-4">
                <div>
                  <p className="text-cream/60 text-xs">Valid</p>
                  <p className="text-sm">{subscription.start_date} → {subscription.end_date || '—'}</p>
                </div>
                <div className="text-right">
                  <p className="text-cream/60 text-xs">Locked price</p>
                  <p className="font-display text-2xl font-semibold">₹{subscription.locked_price}</p>
                </div>
              </div>
            </div>
            {subscription.status === 'active' && (
              <button
                onClick={handleCancel}
                className="w-full text-sm font-medium text-cream/80 hover:text-red bg-black/10 hover:bg-black/20 transition py-3"
              >
                Cancel subscription
              </button>
            )}
          </div>

          {message && (
            <div className="text-sm text-ink/70 bg-ink/5 rounded-lg px-3 py-2 mt-4">{message}</div>
          )}
          </>
        ) : (
          <>
            <div>
              <h2 className="font-display text-lg font-semibold text-ink mb-3">Choose a plan</h2>
              <div className="grid grid-cols-2 gap-3">
                {Object.entries(PLAN_META).map(([key, { label, desc, icon: Icon }]) => (
                  <button
                    key={key}
                    onClick={() => setPlanType(key)}
                    className={`text-left p-4 rounded-xl border-2 transition ${
                      planType === key
                        ? 'border-emerald bg-emerald/5'
                        : 'border-ink/10 bg-white hover:border-ink/20'
                    }`}
                  >
                    <Icon className={`w-5 h-5 mb-2 ${planType === key ? 'text-emerald-dark' : 'text-ink/40'}`} />
                    <p className="text-sm font-semibold text-ink">{label}</p>
                    <p className="text-xs text-ink/50 mt-0.5">{desc}</p>
                  </button>
                ))}
              </div>
            </div>

            <div>
              <h2 className="font-display text-lg font-semibold text-ink mb-3">Pick your dates</h2>
              <p className="text-xs text-ink/50 mb-3">Minimum 7 days — skip the days you'll be away.</p>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-ink/60 mb-1.5">From</label>
                  <input
                    type="date"
                    value={startDate}
                    min={new Date().toISOString().split('T')[0]}
                    onChange={(e) => setStartDate(e.target.value)}
                    className="w-full px-3 py-2.5 rounded-lg border border-ink/10 bg-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-ink/60 mb-1.5">To</label>
                  <input
                    type="date"
                    value={endDate}
                    min={startDate || new Date().toISOString().split('T')[0]}
                    onChange={(e) => setEndDate(e.target.value)}
                    className="w-full px-3 py-2.5 rounded-lg border border-ink/10 bg-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald"
                  />
                </div>
              </div>
            </div>

            {(preview || previewLoading || previewError) && (
              <div className="bg-white rounded-xl border border-ink/5 shadow-sm p-4">
                {previewLoading ? (
                  <div className="flex items-center gap-2 text-sm text-ink/50">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Calculating price…
                  </div>
                ) : previewError ? (
                  <p className="text-sm text-red">{previewError}</p>
                ) : preview ? (
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm text-ink/60">{preview.days} days</p>
                      <p className="text-xs text-ink/40">₹{preview.monthly_price}/month rate</p>
                    </div>
                    <p className="font-display text-2xl font-semibold text-emerald-dark">
                      ₹{preview.calculated_price}
                    </p>
                  </div>
                ) : null}
              </div>
            )}

            {message && (
              <div className="text-sm text-ink/70 bg-ink/5 rounded-lg px-3 py-2">{message}</div>
            )}

            <button
              onClick={handleRequest}
              disabled={!preview}
              className="w-full bg-emerald hover:bg-emerald-dark disabled:opacity-40 disabled:cursor-not-allowed text-white font-medium py-3.5 rounded-xl transition"
            >
              Request this plan
            </button>
          </>
        )}

        {!hasActive && message && (
          <div className="text-sm text-ink/70 bg-ink/5 rounded-lg px-3 py-2">{message}</div>
        )}

        <Link to="/" className="block text-center text-sm text-teal-700 font-medium hover:underline pt-2">
          ← Back to dashboard
        </Link>
      </main>
    </div>
  )
}

export default Subscription