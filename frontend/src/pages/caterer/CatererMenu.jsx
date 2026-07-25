import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../../api/axios'

function CatererMenu() {
  const [menus, setMenus] = useState([])
  const [date, setDate] = useState('')
  const [slot, setSlot] = useState('breakfast')
  const [items, setItems] = useState('')
  const [message, setMessage] = useState('')

  useEffect(() => {
    fetchMenus()
  }, [])

  const fetchMenus = async () => {
    try {
      const res = await api.get('/caterer/menu')
      setMenus(res.data)
    } catch (err) {
      console.error(err)
    }
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setMessage('')
    try {
      await api.post('/caterer/menu', { date, slot, items })
      setMessage('Menu created')
      setItems('')
      fetchMenus()
    } catch (err) {
      setMessage(err.response?.data?.detail || 'Failed to create menu')
    }
  }

  return (
    <div>
      <h2>Menu Management</h2>

      <form onSubmit={handleSubmit}>
        <input
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
          required
        />
        <select value={slot} onChange={(e) => setSlot(e.target.value)}>
          <option value="breakfast">Breakfast</option>
          <option value="lunch">Lunch</option>
          <option value="dinner">Dinner</option>
        </select>
        <input
          type="text"
          placeholder="Items (comma separated)"
          value={items}
          onChange={(e) => setItems(e.target.value)}
          required
        />
        <button type="submit">Add Menu</button>
      </form>

      {message && <p>{message}</p>}

      <h3>Today's Menus</h3>
      {menus.length > 0 ? (
        menus.map((m) => (
          <div key={m.id}>
            <strong>{m.slot}</strong>: {m.items} ({m.date})
          </div>
        ))
      ) : (
        <p>No menus for today</p>
      )}

      <Link to="/caterer">Back to Dashboard</Link>
    </div>
  )
}

export default CatererMenu