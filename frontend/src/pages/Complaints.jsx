import { useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../api/axios'

function Complaints() {
  const [text, setText] = useState('')
  const [category, setCategory] = useState('food_quality')
  const [message, setMessage] = useState('')

  const handleSubmit = async (e) => {
    e.preventDefault()
    setMessage('')
    try {
      await api.post('/student/complaint', { text, category })
      setMessage('Complaint submitted')
      setText('')
    } catch (err) {
      setMessage(err.response?.data?.detail || 'Submission failed')
    }
  }

  return (
    <div>
      <h2>Submit Complaint</h2>

      <form onSubmit={handleSubmit}>
        <select value={category} onChange={(e) => setCategory(e.target.value)}>
          <option value="food_quality">Food Quality</option>
          <option value="hygiene">Hygiene</option>
          <option value="service">Service</option>
          <option value="other">Other</option>
        </select>
        <textarea
          placeholder="Describe your complaint..."
          value={text}
          onChange={(e) => setText(e.target.value)}
          required
        />
        <button type="submit">Submit</button>
      </form>

      {message && <p>{message}</p>}

      <Link to="/">Back to Dashboard</Link>
    </div>
  )
}

export default Complaints