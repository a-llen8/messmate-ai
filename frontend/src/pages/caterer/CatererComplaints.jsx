import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../../api/axios'

function CatererComplaints() {
  const [complaints, setComplaints] = useState([])
  const [message, setMessage] = useState('')

  useEffect(() => {
    fetchComplaints()
  }, [])

  const fetchComplaints = async () => {
    try {
      const res = await api.get('/caterer/complaints')
      setComplaints(res.data)
    } catch (err) {
      console.error(err)
    }
  }

  const handleResolve = async (id) => {
    setMessage('')
    try {
      await api.put(`/caterer/complaints/${id}/resolve`)
      setMessage(`Complaint ${id} resolved`)
      fetchComplaints()
    } catch (err) {
      setMessage(err.response?.data?.detail || 'Resolve failed')
    }
  }

  return (
    <div>
      <h2>Complaints</h2>

      {message && <p>{message}</p>}

      {complaints.length > 0 ? (
        complaints.map((c) => (
          <div key={c.id}>
            <p>
              User #{c.user_id} | {c.category} | {c.text} | {c.created_at}
            </p>
            <button onClick={() => handleResolve(c.id)}>Mark Resolved</button>
          </div>
        ))
      ) : (
        <p>No open complaints</p>
      )}

      <Link to="/caterer">Back to Dashboard</Link>
    </div>
  )
}

export default CatererComplaints