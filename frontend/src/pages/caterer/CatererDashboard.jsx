import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import api from '../../api/axios'

function CatererDashboard() {
  const [stats, setStats] = useState(null)
  const navigate = useNavigate()

  useEffect(() => {
    fetchStats()
  }, [])

  const fetchStats = async () => {
    try {
      const res = await api.get('/caterer/dashboard')
      setStats(res.data)
    } catch (err) {
      console.error(err)
    }
  }

  const handleLogout = () => {
    localStorage.removeItem('token')
    localStorage.removeItem('role')
    navigate('/login')
  }

  if (!stats) return <p>Loading...</p>

  return (
    <div>
      <h2>Caterer Dashboard</h2>
      <button onClick={handleLogout}>Logout</button>

      <div>
        <p>Total Students: {stats.total_students}</p>
        <p>Active Subscriptions: {stats.active_subs}</p>
        <p>Today's Attendance: {stats.today_attendance}</p>
        <p>Open Complaints: {stats.open_complaints}</p>
        <p>Pending Requests: {stats.pending_requests}</p>
      </div>

      <nav>
        <Link to="/caterer/menu">Menu</Link> |{' '}
        <Link to="/caterer/requests">Subscription Requests</Link> |{' '}
        <Link to="/caterer/complaints">Complaints</Link> |{' '}
        <Link to="/caterer/scan">Scan QR</Link>
      </nav>
    </div>
  )
}

export default CatererDashboard