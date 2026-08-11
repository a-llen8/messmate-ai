import { useEffect, useState } from 'react'
import {
  HeartHandshake, ChefHat, MessageCircleWarning, Sparkles,
  Check, X, Pencil, ClipboardCheck,
} from 'lucide-react'
import api from '../../api/axios'
import CatererLayout from '../../components/CatererLayout'

const CATEGORY_META = {
  churn_retention:     { label: 'Retention',          icon: HeartHandshake,       accent: 'text-teal-700',     bg: 'bg-teal-800/10' },
  headcount_prep:      { label: 'Prep',                icon: ChefHat,              accent: 'text-emerald-dark', bg: 'bg-emerald/10' },
  complaint_followup:  { label: 'Complaint follow-up', icon: MessageCircleWarning, accent: 'text-red',          bg: 'bg-red/10' },
  general:             { label: 'General',             icon: Sparkles,             accent: 'text-ink/60',       bg: 'bg-ink/5' },
}

const PRIORITY_META = {
  high:   { label: 'High priority',   border: 'border-red',    dot: 'bg-red' },
  medium: { label: 'Medium priority', border: 'border-amber',  dot: 'bg-amber' },
  low:    { label: 'Low priority',    border: 'border-ink/15', dot: 'bg-ink/25' },
}

// Which tool feeds which cadence — mirrors backend/app/agents/tools.py's
// TOOL_CADENCE. Kept as display copy here since the health endpoint returns
// mode keys (daily/weekly/monthly), not tool names.
const CADENCE_META = {
  daily:   { label: 'Daily',   tool: 'Headcount forecast' },
  weekly:  { label: 'Weekly',  tool: 'Churn risk' },
  monthly: { label: 'Monthly', tool: 'Complaint clusters' },
}

function timeAgo(iso) {
  if (!iso) return null
  const diffMs = Date.now() - new Date(iso).getTime()
  const mins = Math.round(diffMs / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.round(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.round(hrs / 24)
  return `${days}d ago`
}

function HealthStrip({ health, loading }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
      {['daily', 'weekly', 'monthly'].map((key) => {
        const meta = CADENCE_META[key]
        const data = health?.[key]

        let dotColor = 'bg-ink/15'
        let statusText = 'No runs yet'
        if (data?.status === 'completed') { dotColor = 'bg-emerald'; statusText = timeAgo(data.created_at) }
        else if (data?.status === 'incomplete') { dotColor = 'bg-amber'; statusText = `Incomplete · ${timeAgo(data.created_at)}` }
        else if (data?.status === 'error') { dotColor = 'bg-red'; statusText = `Error · ${timeAgo(data.created_at)}` }

        return (
          <div key={key} className="bg-white rounded-xl border border-ink/10 px-5 py-4">
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-xs font-semibold text-ink/70 uppercase tracking-wide">{meta.label}</span>
              <span className={`w-2 h-2 rounded-full ${loading ? 'bg-ink/10 animate-pulse' : dotColor}`} />
            </div>
            <p className="text-sm font-medium text-ink">{meta.tool}</p>
            <p className="text-xs text-ink/40 mt-1">{loading ? '…' : statusText}</p>
          </div>
        )
      })}
    </div>
  )
}

function CatererAgentReview() {
  const [actions, setActions] = useState([])
  const [health, setHealth] = useState(null)
  const [loading, setLoading] = useState(true)
  const [healthLoading, setHealthLoading] = useState(true)
  const [message, setMessage] = useState('')
  const [isError, setIsError] = useState(false)
  const [busyId, setBusyId] = useState(null)
  const [editingId, setEditingId] = useState(null)
  const [editText, setEditText] = useState('')

  useEffect(() => {
    fetchActions()
    fetchHealth()
  }, [])

  const fetchActions = async () => {
    try {
      const res = await api.get('/caterer/agent-actions')
      setActions(res.data)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const fetchHealth = async () => {
    try {
      const res = await api.get('/caterer/agent-runs/health')
      setHealth(res.data)
    } catch (err) {
      console.error(err)
    } finally {
      setHealthLoading(false)
    }
  }

  const startEdit = (action) => {
    setMessage('')
    setEditingId(action.id)
    setEditText(action.drafted_message || '')
  }

  const cancelEdit = () => {
    setEditingId(null)
    setEditText('')
  }

  const handleApprove = async (id) => {
    setMessage('')
    setBusyId(id)
    try {
      await api.post(`/caterer/agent-actions/${id}/approve`)
      setMessage('Action approved')
      setIsError(false)
      setActions((prev) => prev.filter((a) => a.id !== id))
    } catch (err) {
      setMessage(err.response?.data?.detail || 'Approve failed')
      setIsError(true)
    } finally {
      setBusyId(null)
    }
  }

  const handleSaveEdit = async (id) => {
    if (!editText.trim()) {
      setMessage('Drafted message cannot be empty')
      setIsError(true)
      return
    }
    setMessage('')
    setBusyId(id)
    try {
      await api.post(`/caterer/agent-actions/${id}/edit`, { drafted_message: editText.trim() })
      setMessage('Action edited and approved')
      setIsError(false)
      setActions((prev) => prev.filter((a) => a.id !== id))
      setEditingId(null)
      setEditText('')
    } catch (err) {
      setMessage(err.response?.data?.detail || 'Edit failed')
      setIsError(true)
    } finally {
      setBusyId(null)
    }
  }

  const handleReject = async (id) => {
    setMessage('')
    setBusyId(id)
    try {
      await api.post(`/caterer/agent-actions/${id}/reject`)
      setMessage('Action rejected')
      setIsError(false)
      setActions((prev) => prev.filter((a) => a.id !== id))
    } catch (err) {
      setMessage(err.response?.data?.detail || 'Reject failed')
      setIsError(true)
    } finally {
      setBusyId(null)
    }
  }

  return (
    <CatererLayout
      title="Agent Recommendations"
      subtitle="What the Ops Agent found — review, edit, or dismiss each item. Nothing sends until you approve it."
    >
      <HealthStrip health={health} loading={healthLoading} />

      {message && (
        <div className={`text-sm rounded-lg px-3 py-2 mb-4 ${isError ? 'text-red bg-red/10' : 'text-emerald-dark bg-emerald/10'}`}>
          {message}
        </div>
      )}

      {!loading && (
        <p className="text-xs font-medium text-ink/50 uppercase tracking-wide mb-3">
          {actions.length} pending recommendation{actions.length !== 1 ? 's' : ''}
        </p>
      )}

      {loading ? (
        <div className="bg-white rounded-xl border border-ink/10 p-5 text-sm text-ink/40 animate-pulse">Loading…</div>
      ) : actions.length === 0 ? (
        <div className="bg-white rounded-xl border border-ink/10 p-10 text-center">
          <ClipboardCheck className="w-6 h-6 text-ink/20 mx-auto mb-2" />
          <p className="text-sm text-ink/50">All caught up — no pending recommendations.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {actions.map((action) => {
            const catMeta = CATEGORY_META[action.category]
              || { label: action.category, icon: Sparkles, accent: 'text-ink/60', bg: 'bg-ink/5' }
            const priMeta = PRIORITY_META[action.priority]
              || { label: action.priority, border: 'border-ink/15', dot: 'bg-ink/25' }
            const Icon = catMeta.icon
            const isEditing = editingId === action.id
            const isBusy = busyId === action.id

            return (
              <div
                key={action.id}
                className={`bg-white rounded-xl border border-ink/10 border-l-4 ${priMeta.border} p-6`}
              >
                <div className="flex items-start justify-between gap-4 mb-3">
                  <div className="flex items-center gap-3">
                    <div className={`w-9 h-9 rounded-full ${catMeta.bg} flex items-center justify-center shrink-0`}>
                      <Icon className={`w-4 h-4 ${catMeta.accent}`} />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-semibold text-ink/70">{catMeta.label}</span>
                        <span className="inline-flex items-center gap-1 text-xs text-ink/40">
                          <span className={`w-1.5 h-1.5 rounded-full ${priMeta.dot}`} />
                          {priMeta.label}
                        </span>
                      </div>
                      {(action.related_user_id || action.related_date) && (
                        <p className="text-xs text-ink/40 mt-0.5">
                          {action.related_user_id && `Student #${action.related_user_id}`}
                          {action.related_user_id && action.related_date && ' · '}
                          {action.related_date && `for ${action.related_date}`}
                        </p>
                      )}
                    </div>
                  </div>
                  <span className="text-xs text-ink/30 shrink-0">{action.created_at}</span>
                </div>

                <p className="text-[15px] font-semibold text-ink leading-snug mb-4">{action.summary}</p>

                <div className="border-l-2 border-ink/10 pl-3.5 mb-4">
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-ink/40 mb-1">Why</p>
                  <p className="text-sm text-ink/70 leading-relaxed">{action.reasoning}</p>
                </div>

                {(action.drafted_message || isEditing) && (
                  <div className="mb-5">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-ink/40 mb-1.5">Drafted message</p>
                    {isEditing ? (
                      <textarea
                        value={editText}
                        onChange={(e) => setEditText(e.target.value)}
                        rows={3}
                        className="w-full px-3.5 py-3 rounded-lg border border-ink/10 bg-cream-dim text-sm text-ink placeholder:text-ink/30 focus:outline-none focus:ring-2 focus:ring-emerald transition resize-none"
                      />
                    ) : (
                      <div className="bg-cream-dim rounded-lg p-3.5 text-sm text-ink">
                        {action.drafted_message}
                      </div>
                    )}
                  </div>
                )}

                <div className="flex items-center gap-2">
                  {isEditing ? (
                    <>
                      <button
                        onClick={() => handleSaveEdit(action.id)}
                        disabled={isBusy}
                        className="inline-flex items-center gap-1.5 bg-emerald hover:bg-emerald-dark disabled:opacity-40 text-white text-sm font-medium px-3 py-2 rounded-lg transition"
                      >
                        <Check className="w-4 h-4" />
                        Save & approve
                      </button>
                      <button
                        onClick={cancelEdit}
                        disabled={isBusy}
                        className="inline-flex items-center gap-1.5 bg-white border border-ink/10 hover:bg-ink/5 disabled:opacity-40 text-ink/70 text-sm font-medium px-3 py-2 rounded-lg transition"
                      >
                        Cancel
                      </button>
                    </>
                  ) : (
                    <>
                      <button
                        onClick={() => handleApprove(action.id)}
                        disabled={isBusy}
                        className="inline-flex items-center gap-1.5 bg-emerald hover:bg-emerald-dark disabled:opacity-40 text-white text-sm font-medium px-3 py-2 rounded-lg transition"
                      >
                        <Check className="w-4 h-4" />
                        Approve
                      </button>
                      {action.drafted_message && (
                        <button
                          onClick={() => startEdit(action)}
                          disabled={isBusy}
                          className="inline-flex items-center gap-1.5 bg-white border border-ink/10 hover:bg-ink/5 disabled:opacity-40 text-ink/70 text-sm font-medium px-3 py-2 rounded-lg transition"
                        >
                          <Pencil className="w-4 h-4" />
                          Edit
                        </button>
                      )}
                      <button
                        onClick={() => handleReject(action.id)}
                        disabled={isBusy}
                        className="inline-flex items-center gap-1.5 bg-white border border-ink/10 hover:bg-red/5 hover:border-red/30 disabled:opacity-40 text-ink/70 hover:text-red text-sm font-medium px-3 py-2 rounded-lg transition"
                      >
                        <X className="w-4 h-4" />
                        Reject
                      </button>
                    </>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </CatererLayout>
  )
}

export default CatererAgentReview