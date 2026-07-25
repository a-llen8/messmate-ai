import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../../api/axios'

function CatererRequests() {
  const [requests, setRequests] = useState([])
  const [prices, setPrices] = useState({})
  const [message, setMessage] = useState('')

  useEffect(() => {
    fetchRequests()
  }, [])

  const fetchRequests = async () => {
    try {
      const res = await api.get('/caterer/subscriptions/requests')
      setRequests(res.data)
    } catch (err) {
      console.error(err)
    }
  }

  const handleApprove = async (id, type) => {
    setMessage('')
    try {
      const body = type === 'new' ? { locked_price: parseFloat(prices[id] || 0) } : {}
      await api.post(`/caterer/subscriptions/requests/${id}/approve`, body)
      setMessage(`Request ${id} approved`)
      fetchRequests()
    } catch (err) {
      setMessage(err.response?.data?.detail || 'Approve failed')
    }
  }

  const handleReject = async (id) => {
    setMessage('')
    try {
      await api.post(`/caterer/subscriptions/requests/${id}/reject`)
      setMessage(`Request ${id} rejected`)
      fetchRequests()
    } catch (err) {
      setMessage(err.response?.data?.detail || 'Reject failed')
    }
  }

  return (
    <div>
      <h2>Subscription Requests</h2>

      {message && <p>{message}</p>}

      {requests.length > 0 ? (
        requests.map((r) => (
          <div key={r.id}>
            <p>
              User #{r.user_id} | Type: {r.type} | Plan: {r.plan_type || 'N/A'} |{' '}
              {r.created_at}
            </p>
            {r.type === 'new' && (
              <input
                type="number"
                placeholder="Price (₹)"
                value={prices[r.id] || ''}
                onChange={(e) => setPrices({ ...prices, [r.id]: e.target.value })}
              />
            )}
            <button onClick={() => handleApprove(r.id, r.type)}>Approve</button>
            <button onClick={() => handleReject(r.id)}>Reject</button>
          </div>
        ))
      ) : (
        <p>No pending requests</p>
      )}

      <Link to="/caterer">Back to Dashboard</Link>
    </div>
  )
}

export default CatererRequests