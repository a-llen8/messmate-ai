import { useEffect, useState } from 'react'
import { Utensils, Sparkles, Users, MoreHorizontal, CheckCircle2, MessageSquare } from 'lucide-react'
import api from '../../api/axios'
import CatererLayout from '../../components/CatererLayout'

const CATEGORY_META = {
  food_quality: { label: 'Food quality', icon: Utensils },
  hygiene:      { label: 'Hygiene',      icon: Sparkles },
  service:      { label: 'Service',      icon: Users },
  other:        { label: 'Other',        icon: MoreHorizontal },
}

function CatererComplaints() {
  const [complaints, setComplaints] = useState([])
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState('')
  const [isError, setIsError] = useState(false)
  const [busyId, setBusyId] = useState(null)

  useEffect(() => {
    fetchComplaints()
  }, [])

  const fetchComplaints = async () => {
    try {
      const res = await api.get('/caterer/complaints')
      setComplaints(res.data)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const handleResolve = async (id) => {
    setMessage('')
    setBusyId(id)
    try {
      await api.put(`/caterer/complaints/${id}/resolve`)
      setMessage('Complaint marked resolved')
      setIsError(false)
      fetchComplaints()
    } catch (err) {
      setMessage(err.response?.data?.detail || 'Resolve failed')
      setIsError(true)
    } finally {
      setBusyId(null)
    }
  }

  return (
    <CatererLayout title="Complaints" subtitle="Open complaints from students, awaiting resolution.">
      {message && (
        <div className={`text-sm rounded-lg px-3 py-2 mb-4 ${isError ? 'text-red bg-red/10' : 'text-emerald-dark bg-emerald/10'}`}>
          {message}
        </div>
      )}

      <div className="bg-white rounded-xl border border-ink/10 divide-y divide-ink/5">
        {loading ? (
          <div className="p-5 text-sm text-ink/40 animate-pulse">Loading…</div>
        ) : complaints.length === 0 ? (
          <div className="p-8 text-center">
            <MessageSquare className="w-6 h-6 text-ink/20 mx-auto mb-2" />
            <p className="text-sm text-ink/50">No open complaints — all caught up.</p>
          </div>
        ) : (
          complaints.map((c) => {
            const meta = CATEGORY_META[c.category] || { label: c.category, icon: MoreHorizontal }
            const Icon = meta.icon
            return (
              <div key={c.id} className="flex items-start gap-4 p-5">
                <div className="w-8 h-8 rounded-full bg-red/10 flex items-center justify-center shrink-0 mt-0.5">
                  <Icon className="w-4 h-4 text-red" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-ink">
                    Student #{c.user_id}
                    <span className="ml-2 text-xs font-medium px-2 py-0.5 rounded-full bg-ink/5 text-ink/60">
                      {meta.label}
                    </span>
                  </p>
                  <p className="text-sm text-ink/70 mt-1">{c.text}</p>
                  <p className="text-xs text-ink/30 mt-1">{c.created_at}</p>
                </div>
                <button
                  onClick={() => handleResolve(c.id)}
                  disabled={busyId === c.id}
                  className="inline-flex items-center gap-1.5 bg-emerald hover:bg-emerald-dark disabled:opacity-40 text-white text-xs font-medium px-3 py-2 rounded-lg transition shrink-0"
                >
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  Resolve
                </button>
              </div>
            )
          })
        )}
      </div>
    </CatererLayout>
  )
}

export default CatererComplaints