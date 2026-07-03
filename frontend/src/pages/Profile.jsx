import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../api/axios'

function Profile() {
  const [profile, setProfile] = useState(null)
  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')
  const [message, setMessage] = useState('')

  useEffect(() => {
    fetchProfile()
  }, [])

  const fetchProfile = async () => {
    try {
      const res = await api.get('/student/profile')
      setProfile(res.data)
      setName(res.data.name)
      setPhone(res.data.phone || '')
    } catch (err) {
      console.error(err)
    }
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setMessage('')
    try {
      await api.put('/student/profile', { name, phone })
      setMessage('Profile updated')
      fetchProfile()
    } catch (err) {
      setMessage('Update failed')
    }
  }

  if (!profile) return <p>Loading...</p>

  return (
    <div>
      <h2>Profile</h2>
      <p>Email: {profile.email}</p>

      <form onSubmit={handleSubmit}>
        <input
          type="text"
          placeholder="Name"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <input
          type="text"
          placeholder="Phone"
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
        />
        <button type="submit">Update</button>
      </form>

      {message && <p>{message}</p>}

      <Link to="/">Back to Dashboard</Link>
    </div>
  )
}

export default Profile