import { useEffect, useRef, useState } from 'react'
import { Html5Qrcode, Html5QrcodeScannerState } from 'html5-qrcode'
import { Search, CheckCircle2, AlertCircle, User as UserIcon } from 'lucide-react'
import api from '../../api/axios'
import CatererLayout from '../../components/CatererLayout'

function CatererScan() {
  const [result, setResult] = useState('')
  const [message, setMessage] = useState('')
  const [isError, setIsError] = useState(false)
  const [searchName, setSearchName] = useState('')
  const [searchResults, setSearchResults] = useState([])
  const scannerRef = useRef(null)

  useEffect(() => {
    let cancelled = false
    const scanner = new Html5Qrcode('reader')
    scannerRef.current = scanner

    const safeClear = () => {
      try {
        scanner.clear()
      } catch (e) {
        // element already gone — nothing to do
      }
    }

    scanner
      .start(
        { facingMode: 'environment' },
        { fps: 10, qrbox: 250 },
        (decodedText) => {
          handleScan(decodedText)
        },
        () => {}
      )
      .then(() => {
        // Effect was cleaned up before start() finished — stop immediately.
        if (cancelled) {
          scanner.stop().then(safeClear).catch(safeClear)
        }
      })
      .catch((err) => {
        console.error(err)
        if (err?.name === 'NotAllowedError') {
          setMessage('Camera permission denied — allow camera access for this site and reload the page.')
          setIsError(true)
        }
      })

    return () => {
      cancelled = true
      if (scanner.getState() === Html5QrcodeScannerState.SCANNING) {
        scanner.stop().then(safeClear).catch(safeClear)
      } else {
        safeClear()
      }
    }
  }, [])

  const handleScan = async (qrData) => {
    setResult(qrData)
    setMessage('')
    try {
      const res = await api.post('/qr/scan', { qr_data: qrData })
      setMessage(`${res.data.student} — ${res.data.slot} recorded`)
      setIsError(false)
    } catch (err) {
      setMessage(err.response?.data?.detail || 'Scan failed')
      setIsError(true)
    }
  }

  const handleSearch = async () => {
    try {
      const res = await api.get(`/qr/search?name=${searchName}`)
      setSearchResults(res.data)
    } catch (err) {
      console.error(err)
    }
  }

  const handleMarkPresent = async (studentId) => {
    setMessage('')
    try {
      const res = await api.post('/qr/manual', { user_id: studentId })
      setMessage(`${res.data.student} — ${res.data.slot} recorded`)
      setIsError(false)
    } catch (err) {
      setMessage(err.response?.data?.detail || 'Could not mark present')
      setIsError(true)
    }
  }

  return (
    <CatererLayout title="Scan" subtitle="Scan student QR codes to record attendance.">
      <div className="grid grid-cols-2 gap-6">
        <div className="bg-white rounded-xl border border-ink/10 p-6">
          <p className="text-sm font-semibold text-ink mb-4">Camera</p>
          <div
            id="reader"
            className="w-full rounded-lg overflow-hidden border border-ink/10 bg-ink/5"
          />

          {result && (
            <p className="text-xs text-ink/40 mt-3 truncate">Last scanned: {result}</p>
          )}

          {message && (
            <div className={`flex items-center gap-2 text-sm rounded-lg px-3 py-2 mt-3 ${isError ? 'text-red bg-red/10' : 'text-emerald-dark bg-emerald/10'}`}>
              {isError ? <AlertCircle className="w-4 h-4 shrink-0" /> : <CheckCircle2 className="w-4 h-4 shrink-0" />}
              {message}
            </div>
          )}
        </div>

        <div className="bg-white rounded-xl border border-ink/10 p-6">
          <p className="text-sm font-semibold text-ink mb-1">Fallback: search by name</p>
          <p className="text-xs text-ink/40 mb-4">If the QR scan isn't working, look the student up here.</p>

          <div className="flex items-center gap-2 mb-4">
            <input
              type="text"
              placeholder="Student name"
              value={searchName}
              onChange={(e) => setSearchName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              className="flex-1 px-3 py-2.5 rounded-lg border border-ink/10 bg-cream-dim text-sm text-ink placeholder:text-ink/30 focus:outline-none focus:ring-2 focus:ring-emerald transition"
            />
            <button
              onClick={handleSearch}
              className="inline-flex items-center gap-1.5 bg-teal-800 hover:bg-teal-700 text-white text-sm font-medium px-3 py-2.5 rounded-lg transition shrink-0"
            >
              <Search className="w-4 h-4" />
              Search
            </button>
          </div>

          <div className="space-y-2">
            {searchResults.map((s) => (
              <div key={s.id} className="flex items-center gap-3 px-3 py-2.5 rounded-lg bg-cream-dim">
                <div className="w-7 h-7 rounded-full bg-teal-800/10 flex items-center justify-center shrink-0">
                  <UserIcon className="w-3.5 h-3.5 text-teal-700" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-ink truncate">{s.name}</p>
                  <p className="text-xs text-ink/40 truncate">{s.email}</p>
                </div>
                <button
                  onClick={() => handleMarkPresent(s.id)}
                  className="text-xs font-medium text-white bg-emerald hover:bg-emerald-dark px-3 py-1.5 rounded-lg transition shrink-0"
                >
                  Mark present
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>
    </CatererLayout>
  )
}

export default CatererScan