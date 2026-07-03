import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import api from '../api/axios'

function Dashboard() {
  const [profile, setProfile] = useState(null)
  const [subscription, setSubscription] = useState(null)
  const [menu, setMenu] = useState(null)
  const navigate = useNavigate()

  useEffect(() => {
    fetchData()
  }, [])

  const fetchData = async () => {
    try {
      const profileRes = await api.get('/student/profile')
      setProfile(profileRes.data)

      const subRes = await api.get('/student/subscription')
      setSubscription(subRes.data)

      const menuRes = await api.get('/student/menu/today')
      setMenu(menuRes.data)
    } catch (err) {
      console.error(err)
    }
  }

  const handleLogout = () => {
    localStorage.removeItem('token')
    localStorage.removeItem('role')
    navigate('/login')
  }

  return (
    <div>
      <h2>Dashboard</h2>
      <button onClick={handleLogout}>Logout</button>

      {profile && <p>Welcome, {profile.name}</p>}

      <h3>Subscription</h3>
      {subscription && subscription.status === 'no subscription' ? (
        <p>No active subscription</p>
      ) : subscription ? (
        <p>Status: {subscription.status} | Plan: {subscription.plan_type}</p>
      ) : (
        <p>Loading...</p>
      )}

      <h3>Today's Menu</h3>
      {menu && Array.isArray(menu) ? (
        menu.map((m, i) => (
          <div key={i}>
            <strong>{m.slot}</strong>: {m.items}
          </div>
        ))
      ) : (
        <p>No menu available</p>
      )}

      <nav>
        <Link to="/profile">Profile</Link> |{' '}
        <Link to="/subscription">Subscription</Link> |{' '}
        <Link to="/menu">Menu</Link> |{' '}
        <Link to="/complaints">Complaints</Link>
      </nav>
    </div>
  )
}

export default Dashboard