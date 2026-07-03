import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../api/axios'

function TodayMenu() {
  const [menu, setMenu] = useState(null)
  const [ratings, setRatings] = useState({})
  const [message, setMessage] = useState('')

  useEffect(() => {
    fetchMenu()
  }, [])

  const fetchMenu = async () => {
    try {
      const res = await api.get('/student/menu/today')
      setMenu(res.data)
    } catch (err) {
      console.error(err)
    }
  }

  const handleRate = async (menuId, score) => {
    setMessage('')
    try {
      await api.post('/student/rating', { menu_id: menuId, score })
      setMessage('Rating submitted')
      setRatings({ ...ratings, [menuId]: score })
    } catch (err) {
      setMessage(err.response?.data?.detail || 'Rating failed')
    }
  }

  if (!menu) return <p>Loading...</p>

  return (
    <div>
      <h2>Today's Menu</h2>

      {Array.isArray(menu) && menu.length > 0 ? (
        menu.map((m, i) => (
          <div key={i}>
            <h3>{m.slot}</h3>
            <p>{m.items}</p>
            <div>
              Rate:
              {[1, 2, 3, 4, 5].map((star) => (
                <button key={star} onClick={() => handleRate(m.id, star)}>
                  {star}
                </button>
              ))}
            </div>
          </div>
        ))
      ) : (
        <p>No menu available for today</p>
      )}

      {message && <p>{message}</p>}

      <Link to="/">Back to Dashboard</Link>
    </div>
  )
}

export default TodayMenu