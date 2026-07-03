import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../api/axios'

function Subscription() {
  const [subscription, setSubscription] = useState(null)
  const [planType, setPlanType] = useState('full')
  const [message, setMessage] = useState('')

  useEffect(() => {
    fetchSubscription()
  }, [])

  const fetchSubscription = async () => {
    try {
      const res = await api.get('/student/subscription')
      setSubscription(res.data)
    } catch (err) {
      console.error(err)
    }
  }

  const handleRequest = async (e) => {
    e.preventDefault()
    setMessage('')
    try {
      await api.post('/student/subscription/request', { plan_type: planType })
      setMessage('Subscription request submitted')
      fetchSubscription()
    } catch (err) {
      setMessage(err.response?.data?.detail || 'Request failed')
    }
  }

  const handleCancel = async () => {
    setMessage('')
    try {
      await api.post('/student/subscription/cancel')
      setMessage('Cancellation request submitted')
      fetchSubscription()
    } catch (err) {
      setMessage(err.response?.data?.detail || 'Cancel failed')
    }
  }

  if (!subscription) return <p>Loading...</p>

  return (
    <div>
      <h2>Subscription</h2>

      {subscription.status === 'no subscription' ? (
        <div>
          <p>No active subscription</p>
          <form onSubmit={handleRequest}>
            <select value={planType} onChange={(e) => setPlanType(e.target.value)}>
              <option value="full">Full (Breakfast + Lunch + Dinner)</option>
              <option value="lunch_only">Lunch Only</option>
              <option value="dinner_only">Dinner Only</option>
            </select>
            <button type="submit">Request Subscription</button>
          </form>
        </div>
      ) : (
        <div>
          <p>Status: {subscription.status}</p>
          <p>Plan: {subscription.plan_type}</p>
          <p>Start Date: {subscription.start_date}</p>
          <p>Locked Price: ₹{subscription.locked_price}</p>
          {subscription.status === 'active' && (
            <button onClick={handleCancel}>Cancel Subscription</button>
          )}
        </div>
      )}

      {message && <p>{message}</p>}

      <Link to="/">Back to Dashboard</Link>
    </div>
  )
}

export default Subscription