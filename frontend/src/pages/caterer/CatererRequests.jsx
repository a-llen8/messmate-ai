import { useEffect, useState } from 'react'
import { Check, X, ClipboardList } from 'lucide-react'
import api from '../../api/axios'
import CatererLayout from '../../components/CatererLayout'

function CatererRequests() {
  const [requests, setRequests] = useState([])
  const [loading, setLoading] = useState(true)
  const [prices, setPrices] = useState({})
  const [message, setMessage] = useState('')
  const [isError, setIsError] = useState(false)
  const [busyId, setBusyId] = useState(null)

  useEffect(() => {
    fetchRequests()
  }, [])

  const fetchRequests = async () => {
    try {
      const res = await api.get('/caterer/subscriptions/requests')
      setRequests(res.data)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const handleApprove = async (id, type) => {
    setMessage('')
    setBusyId(id)
    try {
      const raw = prices[id]
      const body = type === 'new' && raw ? { locked_price: parseFloat(raw) } : {}
      await api.post(`/caterer/subscriptions/requests/${id}/approve`, body)
      setMessage('Request approved')
      setIsError(false)
      fetchRequests()
    } catch (err) {
      setMessage(err.response?.data?.detail || 'Approve failed')
      setIsError(true)
    } finally {
      setBusyId(null)
    }
  }

  const handleReject = async (id) => {
    setMessage('')
    setBusyId(id)
    try {
      await api.post(`/caterer/subscriptions/requests/${id}/reject`)
      setMessage('Request rejected')
      setIsError(false)
      fetchRequests()
    } catch (err) {
      setMessage(err.response?.data?.detail || 'Reject failed')
      setIsError(true)
    } finally {
      setBusyId(null)
    }
  }

  const dayCount = (start, end) => {
    if (!start || !end) return null
    const days = Math.round((new Date(end) - new Date(start)) / 86400000) + 1
    return days > 0 ? days : null
  }

  return (
    <CatererLayout title="Requests" subtitle="Approve or reject pending subscription requests.">
      {message && (
        <div className={`text-sm rounded-lg px-3 py-2 mb-4 ${isError ? 'text-red bg-red/10' : 'text-emerald-dark bg-emerald/10'}`}>
          {message}
        </div>
      )}

      <div className="bg-white rounded-xl border border-ink/10 divide-y divide-ink/5">
        {loading ? (
          <div className="p-5 text-sm text-ink/40 animate-pulse">Loading…</div>
        ) : requests.length === 0 ? (
          <div className="p-8 text-center">
            <ClipboardList className="w-6 h-6 text-ink/20 mx-auto mb-2" />
            <p className="text-sm text-ink/50">No pending requests.</p>
          </div>
        ) : (
          requests.map((r) => {
            const days = dayCount(r.start_date, r.end_date)
            return (
              <div key={r.id} className="p-5">
                <div className="flex items-start justify-between gap-4 mb-3">
                  <div>
                    <p className="text-sm font-semibold text-ink">
                      Student #{r.user_id}
                      <span className="ml-2 text-xs font-medium px-2 py-0.5 rounded-full bg-teal-800/10 text-teal-700 capitalize">
                        {r.type}
                      </span>
                    </p>
                    <p className="text-xs text-ink/50 mt-1">
                      Plan: {r.plan_type || 'N/A'}
                      {r.start_date && r.end_date && (
                        <> · {r.start_date} → {r.end_date}{days ? ` (${days} days)` : ''}</>
                      )}
                    </p>
                    <p className="text-xs text-ink/30 mt-0.5">Requested {r.created_at}</p>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  {r.type === 'new' && (
                    <input
                      type="number"
                      placeholder="Override price (₹, optional)"
                      value={prices[r.id] || ''}
                      onChange={(e) => setPrices({ ...prices, [r.id]: e.target.value })}
                      className="flex-1 px-3 py-2 rounded-lg border border-ink/10 bg-cream-dim text-sm text-ink placeholder:text-ink/30 focus:outline-none focus:ring-2 focus:ring-emerald transition"
                    />
                  )}
                  <button
                    onClick={() => handleApprove(r.id, r.type)}
                    disabled={busyId === r.id}
                    className="inline-flex items-center gap-1.5 bg-emerald hover:bg-emerald-dark disabled:opacity-40 text-white text-sm font-medium px-3 py-2 rounded-lg transition"
                  >
                    <Check className="w-4 h-4" />
                    Approve
                  </button>
                  <button
                    onClick={() => handleReject(r.id)}
                    disabled={busyId === r.id}
                    className="inline-flex items-center gap-1.5 bg-white border border-ink/10 hover:bg-red/5 hover:border-red/30 disabled:opacity-40 text-ink/70 hover:text-red text-sm font-medium px-3 py-2 rounded-lg transition"
                  >
                    <X className="w-4 h-4" />
                    Reject
                  </button>
                </div>
              </div>
            )
          })
        )}
      </div>
    </CatererLayout>
  )
}

export default CatererRequests