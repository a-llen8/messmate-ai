import { useEffect, useState } from 'react'
import { CalendarDays, MessageSquareText, Star, UtensilsCrossed } from 'lucide-react'
import api from '../../api/axios'
import CatererLayout from '../../components/CatererLayout'

function formatDate(value) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString()
}

function CatererRatings() {
  const [ratings, setRatings] = useState([])
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState('')
  const [isError, setIsError] = useState(false)

  useEffect(() => {
    fetchRatings()
  }, [])

  const fetchRatings = async () => {
    try {
      const res = await api.get('/caterer/ratings')
      setRatings(res.data)
    } catch (err) {
      console.error(err)
      setMessage(err.response?.data?.detail || 'Could not load ratings')
      setIsError(true)
    } finally {
      setLoading(false)
    }
  }

  return (
    <CatererLayout title="Ratings" subtitle="Recent menu feedback from students.">
      {message && (
        <div className={`text-sm rounded-lg px-3 py-2 mb-4 ${isError ? 'text-red bg-red/10' : 'text-emerald-dark bg-emerald/10'}`}>
          {message}
        </div>
      )}

      <div className="space-y-4">
        {loading ? (
          <div className="bg-white rounded-xl border border-ink/10 p-5 text-sm text-ink/40 animate-pulse">
            Loading ratings…
          </div>
        ) : ratings.length === 0 ? (
          <div className="bg-white rounded-xl border border-ink/10 p-8 text-center">
            <Star className="w-6 h-6 text-ink/20 mx-auto mb-2" />
            <p className="text-sm text-ink/50">No ratings yet for recent menus.</p>
          </div>
        ) : (
          ratings.map((item) => (
            <div key={item.menu_id} className="bg-white rounded-xl border border-ink/10 p-5">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 text-sm text-ink/60">
                    <UtensilsCrossed className="w-4 h-4" />
                    <span className="font-medium text-ink">{item.slot}</span>
                  </div>
                  <p className="mt-2 text-sm font-semibold text-ink">{item.items}</p>
                  <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-ink/40">
                    <span className="inline-flex items-center gap-1">
                      <CalendarDays className="w-3.5 h-3.5" />
                      {formatDate(item.date)}
                    </span>
                    <span>{item.count} rating{item.count === 1 ? '' : 's'}</span>
                  </div>
                </div>

                <div className="shrink-0 rounded-lg bg-amber-50 px-3 py-2 text-right">
                  <div className="flex items-center justify-end gap-1 text-amber-600">
                    <Star className="w-4 h-4 fill-current" />
                    <span className="text-sm font-semibold text-ink">{item.avg_score}/5</span>
                  </div>
                  <p className="text-xs text-ink/50 mt-0.5">Average score</p>
                </div>
              </div>

              <div className="mt-4 rounded-lg bg-cream-dim p-3">
                <div className="flex items-center gap-2 text-sm font-medium text-ink">
                  <MessageSquareText className="w-4 h-4" />
                  Student comments
                </div>
                {item.comments && item.comments.length > 0 ? (
                  <ul className="mt-2 space-y-2 text-sm text-ink/70">
                    {item.comments.map((comment, idx) => (
                      <li key={`${item.menu_id}-${idx}`} className="rounded-md bg-white px-3 py-2">
                        {comment}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-2 text-sm text-ink/50">No comments submitted yet.</p>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </CatererLayout>
  )
}

export default CatererRatings
