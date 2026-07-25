import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, User, Phone, Mail } from 'lucide-react'
import api from '../api/axios'

function Profile() {
  const [profile, setProfile] = useState(null)
  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')
  const [message, setMessage] = useState('')
  const [saving, setSaving] = useState(false)

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
    setSaving(true)
    try {
      await api.put('/student/profile', { name, phone })
      setMessage('Profile updated.')
      fetchProfile()
    } catch (err) {
      setMessage('Could not update profile.')
    } finally {
      setSaving(false)
    }
  }

  if (!profile) {
    return (
      <div className="min-h-screen bg-cream flex items-center justify-center">
        <div className="animate-pulse text-ink/40 text-sm">Loading…</div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-cream pb-16">
      <header className="px-6 pt-8 pb-4">
        <Link to="/" className="inline-flex items-center gap-1.5 text-sm text-ink/50 hover:text-ink mb-4">
          <ArrowLeft className="w-4 h-4" />
          Back
        </Link>
        <h1 className="font-display text-2xl font-semibold text-ink">Profile</h1>
      </header>

      <main className="px-6">
        <div className="bg-white rounded-2xl shadow-sm border border-ink/5 p-5 mb-6 flex items-center gap-3">
          <div className="w-12 h-12 rounded-full bg-teal-800 flex items-center justify-center text-cream font-display text-lg font-semibold">
            {profile.name?.[0]?.toUpperCase()}
          </div>
          <div>
            <p className="font-semibold text-ink">{profile.name}</p>
            <p className="text-xs text-ink/50 flex items-center gap-1">
              <Mail className="w-3 h-3" /> {profile.email}
            </p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-ink/70 mb-1.5">Full name</label>
            <div className="relative">
              <User className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-ink/40" />
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full pl-10 pr-4 py-3 rounded-xl border border-ink/10 bg-white text-ink focus:outline-none focus:ring-2 focus:ring-emerald transition"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-ink/70 mb-1.5">Phone</label>
            <div className="relative">
              <Phone className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-ink/40" />
              <input
                type="text"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                className="w-full pl-10 pr-4 py-3 rounded-xl border border-ink/10 bg-white text-ink focus:outline-none focus:ring-2 focus:ring-emerald transition"
              />
            </div>
          </div>

          {message && (
            <div className="text-sm text-emerald-dark bg-emerald/10 rounded-lg px-3 py-2">{message}</div>
          )}

          <button
            type="submit"
            disabled={saving}
            className="w-full bg-emerald hover:bg-emerald-dark disabled:opacity-60 text-white font-medium py-3 rounded-xl transition"
          >
            {saving ? 'Saving…' : 'Save changes'}
          </button>
        </form>
      </main>
    </div>
  )
}

export default Profile