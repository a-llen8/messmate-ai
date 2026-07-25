import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { UtensilsCrossed, Mail, Lock } from 'lucide-react'
import api from '../api/axios'

function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const formData = new URLSearchParams()
      formData.append('username', email)
      formData.append('password', password)

      const res = await api.post('/auth/login', formData, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      })

      localStorage.setItem('token', res.data.access_token)
      localStorage.setItem('role', res.data.role)
      if (res.data.role === 'caterer' || res.data.role === 'admin') {
        navigate('/caterer')
      } else {
        navigate('/')
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Login failed. Check your details and try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex flex-col justify-center px-6 py-12 bg-cream">
      <div className="mx-auto w-full max-w-sm">
        <div className="flex items-center gap-2 mb-10">
          <div className="w-10 h-10 rounded-xl bg-teal-800 flex items-center justify-center">
            <UtensilsCrossed className="w-5 h-5 text-cream" strokeWidth={2} />
          </div>
          <span className="font-display text-2xl font-semibold text-ink">MessMate</span>
        </div>

        <h1 className="font-display text-3xl font-semibold text-ink mb-1">Welcome back</h1>
        <p className="text-ink/60 mb-8">Sign in to check today's menu and your mess card.</p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-ink/70 mb-1.5">Email</label>
            <div className="relative">
              <Mail className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-ink/40" />
              <input
                type="email"
                placeholder="you@college.edu"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="w-full pl-10 pr-4 py-3 rounded-xl border border-ink/10 bg-white text-ink placeholder:text-ink/30 focus:outline-none focus:ring-2 focus:ring-emerald transition"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-ink/70 mb-1.5">Password</label>
            <div className="relative">
              <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-ink/40" />
              <input
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="w-full pl-10 pr-4 py-3 rounded-xl border border-ink/10 bg-white text-ink placeholder:text-ink/30 focus:outline-none focus:ring-2 focus:ring-emerald transition"
              />
            </div>
          </div>

          {error && (
            <div className="text-sm text-red bg-red/10 border border-red/20 rounded-lg px-3 py-2">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-emerald hover:bg-emerald-dark text-white font-medium py-3 rounded-xl transition disabled:opacity-60"
          >
            {loading ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        <p className="text-center text-sm text-ink/60 mt-6">
          New here?{' '}
          <Link to="/register" className="text-teal-700 font-medium hover:underline">
            Create an account
          </Link>
        </p>
      </div>
    </div>
  )
}

export default Login