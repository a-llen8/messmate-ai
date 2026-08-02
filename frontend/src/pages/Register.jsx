import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { UtensilsCrossed, Mail, Lock, User, Phone, Eye, EyeOff } from 'lucide-react'
import api from '../api/axios'

function Register() {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await api.post('/auth/register', { name, email, phone, password })
      setSuccess(true)
      setTimeout(() => navigate('/login'), 1200)
    } catch (err) {
      setError(err.response?.data?.detail || 'Registration failed. Try a different email.')
    } finally {
      setLoading(false)
    }
  }

  const fields = [
    { icon: User, type: 'text', placeholder: 'Full name', value: name, set: setName, label: 'Name' },
    { icon: Mail, type: 'email', placeholder: 'you@college.edu', value: email, set: setEmail, label: 'Email' },
    { icon: Phone, type: 'text', placeholder: '9876543210', value: phone, set: setPhone, label: 'Phone' },
    { icon: Lock, type: 'password', placeholder: '••••••••', value: password, set: setPassword, label: 'Password' },
  ]

  return (
    <div className="min-h-screen flex flex-col justify-center px-6 py-12 bg-cream">
      <div className="mx-auto w-full max-w-sm">
        <div className="flex items-center gap-2 mb-10">
          <div className="w-10 h-10 rounded-xl bg-teal-800 flex items-center justify-center">
            <UtensilsCrossed className="w-5 h-5 text-cream" strokeWidth={2} />
          </div>
          <span className="font-display text-2xl font-semibold text-ink">MessMate</span>
        </div>

        <h1 className="font-display text-3xl font-semibold text-ink mb-1">Create your account</h1>
        <p className="text-ink/60 mb-8">Set up your mess card in under a minute.</p>

        <form onSubmit={handleSubmit} className="space-y-4">
          {fields.map(({ icon: Icon, type, placeholder, value, set, label }) => (
            <div key={label}>
              <label className="block text-sm font-medium text-ink/70 mb-1.5">{label}</label>
              <div className="relative">
                <Icon className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-ink/40" />
                <input
                  type={type === 'password' ? (showPassword ? 'text' : 'password') : type}
                  placeholder={placeholder}
                  value={value}
                  onChange={(e) => set(e.target.value)}
                  required
                  className={`w-full pl-10 py-3 rounded-xl border border-ink/10 bg-white text-ink placeholder:text-ink/30 focus:outline-none focus:ring-2 focus:ring-emerald transition ${type === 'password' ? 'pr-10' : 'pr-4'}`}
                />
                {type === 'password' && (
                  <button
                    type="button"
                    onClick={() => setShowPassword((v) => !v)}
                    className="absolute right-3.5 top-1/2 -translate-y-1/2 text-ink/40 hover:text-ink/70"
                  >
                    {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                )}
              </div>
            </div>
          ))}

          {error && (
            <div className="text-sm text-red bg-red/10 border border-red/20 rounded-lg px-3 py-2">
              {error}
            </div>
          )}
          {success && (
            <div className="text-sm text-emerald-dark bg-emerald/10 border border-emerald/20 rounded-lg px-3 py-2">
              Account created — taking you to sign in…
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-emerald hover:bg-emerald-dark text-white font-medium py-3 rounded-xl transition disabled:opacity-60"
          >
            {loading ? 'Creating account…' : 'Create account'}
          </button>
        </form>

        <p className="text-center text-sm text-ink/60 mt-6">
          Already a member?{' '}
          <Link to="/login" className="text-teal-700 font-medium hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  )
}

export default Register