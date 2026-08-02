import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, QrCode, RefreshCw } from 'lucide-react'
import api from '../api/axios'

const SERVING_WINDOWS = [
  { label: 'Breakfast', range: '7:00 AM – 10:00 AM' },
  { label: 'Lunch',     range: '12:00 PM – 2:30 PM' },
  { label: 'Dinner',    range: '7:00 PM – 9:30 PM' },
]

function GiveAttendance() {
  const [qr, setQr] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const fetchQr = async () => {
    setLoading(true)
    setError('')
    setQr(null)
    try {
      const res = await api.get('/qr/generate')
      setQr(res.data)
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not generate QR')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-cream pb-16">
      <header className="px-6 pt-8 pb-4">
        <Link to="/" className="inline-flex items-center gap-1.5 text-sm text-ink/50 hover:text-ink mb-4">
          <ArrowLeft className="w-4 h-4" />
          Back
        </Link>
        <h1 className="font-display text-2xl font-semibold text-ink">Give attendance</h1>
        <p className="text-ink/50 text-sm mt-1">One QR for the day — show it at whichever meal you're eating.</p>
      </header>

      <main className="px-6 space-y-5">
        <div className="bg-white rounded-2xl shadow-sm border border-ink/5 p-6 flex flex-col items-center justify-center min-h-[280px]">
          {loading ? (
            <div className="animate-pulse text-ink/40 text-sm">Generating…</div>
          ) : error ? (
            <div className="text-center">
              <QrCode className="w-8 h-8 text-ink/20 mx-auto mb-3" />
              <p className="text-sm text-red">{error}</p>
              <button
                onClick={fetchQr}
                className="inline-flex items-center gap-1.5 mt-4 text-sm text-teal-700 font-medium hover:underline"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                Try again
              </button>
            </div>
          ) : qr ? (
            <>
              <img
                src={`data:image/png;base64,${qr.qr_base64}`}
                alt="Attendance QR code"
                className="w-48 h-48 rounded-lg"
              />
              <p className="text-xs text-ink/50 mt-4">{qr.date}</p>
            </>
          ) : (
            <div className="text-center">
              <QrCode className="w-8 h-8 text-ink/20 mx-auto mb-3" />
              <button
                onClick={fetchQr}
                className="mt-1 inline-flex items-center gap-1.5 bg-emerald hover:bg-emerald-dark text-white text-sm font-medium px-4 py-2 rounded-lg transition"
              >
                Generate my QR
              </button>
            </div>
          )}
        </div>

        <div className="bg-white rounded-xl border border-ink/10 divide-y divide-ink/5">
          {SERVING_WINDOWS.map(({ label, range }) => (
            <div key={label} className="flex items-center justify-between px-4 py-3">
              <span className="text-sm font-medium text-ink/80">{label}</span>
              <span className="text-xs text-ink/40">{range}</span>
            </div>
          ))}
        </div>

        <p className="text-xs text-ink/40 text-center">
          Your QR only works during these windows and is valid for today only.
        </p>
      </main>
    </div>
  )
}

export default GiveAttendance