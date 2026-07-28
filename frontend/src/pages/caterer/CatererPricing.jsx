import { useEffect, useState } from 'react'
import { Coffee, Sun, Moon, UtensilsCrossed, Wallet, Save } from 'lucide-react'
import api from '../../api/axios'
import CatererLayout from '../../components/CatererLayout'

const PLAN_META = {
  full:             { label: 'Full plan',          desc: 'Breakfast, lunch & dinner', icon: UtensilsCrossed },
  breakfast_only:   { label: 'Breakfast only',      desc: 'Morning meal only',         icon: Coffee },
  lunch_only:       { label: 'Lunch only',          desc: 'Midday meal only',          icon: Sun },
  dinner_only:      { label: 'Dinner only',         desc: 'Evening meal only',         icon: Moon },
  breakfast_lunch:  { label: 'Breakfast + Lunch',   desc: 'Two meals a day',           icon: Coffee },
  breakfast_dinner: { label: 'Breakfast + Dinner',  desc: 'Two meals a day',           icon: Coffee },
  lunch_dinner:     { label: 'Lunch + Dinner',      desc: 'Two meals a day',           icon: Sun },
}

function CatererPricing() {
  const [plans, setPlans] = useState({})
  const [inputs, setInputs] = useState({})
  const [loading, setLoading] = useState(true)
  const [savingKey, setSavingKey] = useState(null)
  const [message, setMessage] = useState('')
  const [isError, setIsError] = useState(false)

  useEffect(() => {
    fetchPlans()
  }, [])

  const fetchPlans = async () => {
    try {
      const res = await api.get('/caterer/price-plans')
      const map = {}
      res.data.forEach((p) => {
        map[p.plan_type] = p.monthly_price
      })
      setPlans(map)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const handleSave = async (planType) => {
    const value = inputs[planType] ?? plans[planType]
    if (!value) return
    setMessage('')
    setSavingKey(planType)
    try {
      await api.post('/caterer/price-plans', {
        plan_type: planType,
        monthly_price: parseFloat(value),
      })
      setMessage(`${PLAN_META[planType]?.label || planType} price saved`)
      setIsError(false)
      fetchPlans()
    } catch (err) {
      setMessage(err.response?.data?.detail || 'Failed to save price')
      setIsError(true)
    } finally {
      setSavingKey(null)
    }
  }

  return (
    <CatererLayout title="Pricing" subtitle="Set the monthly price for each plan. Students are billed pro-rata by day.">
      {message && (
        <div className={`text-sm rounded-lg px-3 py-2 mb-4 ${isError ? 'text-red bg-red/10' : 'text-emerald-dark bg-emerald/10'}`}>
          {message}
        </div>
      )}

      {loading ? (
        <div className="text-sm text-ink/40 animate-pulse">Loading…</div>
      ) : (
        <div className="bg-white rounded-xl border border-ink/10 divide-y divide-ink/5">
          {Object.entries(PLAN_META).map(([key, { label, desc, icon: Icon }]) => {
            const current = plans[key]
            const value = inputs[key] ?? current ?? ''
            return (
              <div key={key} className="flex items-center gap-4 p-5">
                <div className="w-9 h-9 rounded-full bg-teal-800/10 flex items-center justify-center shrink-0">
                  <Icon className="w-4 h-4 text-teal-700" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-ink">{label}</p>
                  <p className="text-xs text-ink/40">{desc}</p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <div className="relative">
                    <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-ink/40">₹</span>
                    <input
                      type="number"
                      placeholder="Not set"
                      value={value}
                      onChange={(e) => setInputs({ ...inputs, [key]: e.target.value })}
                      className="w-32 pl-7 pr-3 py-2 rounded-lg border border-ink/10 bg-cream-dim text-sm text-ink placeholder:text-ink/30 focus:outline-none focus:ring-2 focus:ring-emerald transition"
                    />
                  </div>
                  <button
                    onClick={() => handleSave(key)}
                    disabled={savingKey === key || !value}
                    className="inline-flex items-center gap-1.5 bg-emerald hover:bg-emerald-dark disabled:opacity-40 text-white text-xs font-medium px-3 py-2 rounded-lg transition"
                  >
                    <Save className="w-3.5 h-3.5" />
                    {savingKey === key ? 'Saving…' : 'Save'}
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      )}

      <div className="flex items-start gap-2 mt-4 px-1">
        <Wallet className="w-4 h-4 text-ink/30 mt-0.5 shrink-0" />
        <p className="text-xs text-ink/40">
          When a student requests a plan with a date range, the price is calculated automatically as
          (monthly price ÷ 30) × number of days, based on the value you set here.
        </p>
      </div>
    </CatererLayout>
  )
}

export default CatererPricing