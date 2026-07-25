import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Html5Qrcode } from 'html5-qrcode'
import api from '../../api/axios'

function CatererScan() {
  const [result, setResult] = useState('')
  const [message, setMessage] = useState('')
  const [searchName, setSearchName] = useState('')
  const [searchResults, setSearchResults] = useState([])
  const scannerRef = useRef(null)

  useEffect(() => {
    const scanner = new Html5Qrcode('reader')
    scannerRef.current = scanner
    let isStarted = false

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
        isStarted = true
      })
      .catch((err) => console.error(err))

    return () => {
      if (isStarted) {
        scanner
          .stop()
          .then(() => {
            scanner.clear()
          })
          .catch(() => {
            scanner.clear()
          })
      } else {
        scanner.clear()
      }
    }
  }, [])

  const handleScan = async (qrData) => {
    setResult(qrData)
    setMessage('')
    try {
      const res = await api.post('/qr/scan', { qr_data: qrData })
      setMessage(`✅ ${res.data.student} — ${res.data.slot} recorded`)
    } catch (err) {
      setMessage(err.response?.data?.detail || 'Scan failed')
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

  return (
    <div>
      <h2>Scan QR — Attendance</h2>

      <div id="reader" style={{ width: '300px' }}></div>

      {result && <p>Last scanned: {result}</p>}
      {message && <p>{message}</p>}

      <h3>Fallback: Search by Name</h3>
      <input
        type="text"
        placeholder="Student name"
        value={searchName}
        onChange={(e) => setSearchName(e.target.value)}
      />
      <button onClick={handleSearch}>Search</button>

      {searchResults.map((s) => (
        <div key={s.id}>
          {s.name} — {s.email}
        </div>
      ))}

      <Link to="/caterer">Back to Dashboard</Link>
    </div>
  )
}

export default CatererScan