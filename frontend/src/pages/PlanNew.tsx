import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiFetch, ApiError } from '../api/client'

function getMonday(weekOffset: number): string {
  const d = new Date()
  const day = d.getDay()
  // Sunday (0) → step back 6 days, other days → step back to Monday
  const daysToCurrentMonday = day === 0 ? -6 : 1 - day
  d.setDate(d.getDate() + daysToCurrentMonday + weekOffset * 7)
  return d.toISOString().slice(0, 10)
}

function formatWeek(iso: string): string {
  const d = new Date(iso + 'T00:00:00')
  const sun = new Date(d)
  sun.setDate(d.getDate() + 6)
  const fmt = (date: Date, year = false) =>
    date.toLocaleDateString('de-DE', {
      day: '2-digit',
      month: '2-digit',
      ...(year ? { year: 'numeric' } : {}),
    })
  return `${fmt(d)} – ${fmt(sun, true)}`
}

export default function PlanNew() {
  const navigate = useNavigate()
  const thisWeek = getMonday(0)
  const nextWeek = getMonday(1)
  const [weekStart, setWeekStart] = useState(nextWeek)
  const [wishText, setWishText] = useState('')
  const [portionOverride, setPortionOverride] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [preparedPlanId, setPreparedPlanId] = useState<number | null>(null)

  async function handleStart() {
    setLoading(true)
    setError('')
    setPreparedPlanId(null)
    const trimmedWish = wishText.trim()
    const portionValue = portionOverride.trim() ? Number(portionOverride) : null
    if (portionValue !== null && (portionValue < 2 || portionValue > 20)) {
      setError('Personenzahl muss zwischen 2 und 20 liegen')
      setLoading(false)
      return
    }
    try {
      const resp = await apiFetch<{ id: number; status: string; message?: string }>('/plans', {
        method: 'POST',
        body: {
          week_start_date: weekStart,
          ...(trimmedWish ? { wish_text: trimmedWish } : {}),
          ...(portionValue !== null ? { portion_override: portionValue } : {}),
        },
      })
      if ((trimmedWish || portionValue !== null) && resp.message === 'Vorschläge bereits vorbereitet') {
        setPreparedPlanId(resp.id)
        setLoading(false)
        return
      }
      navigate(`/plan/${resp.id}`)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Fehler beim Erstellen des Plans')
      setLoading(false)
    }
  }

  return (
    <main className="mx-auto max-w-xl px-4 py-5 sm:p-6">
      <button
        onClick={() => navigate('/')}
        className="mb-4 text-sm text-stone-500 underline hover:text-stone-700"
      >
        Zurück
      </button>

      <h1 className="mb-6 text-2xl font-semibold tracking-tight">Neue Woche planen</h1>

      <div className="rounded-xl border border-stone-200 bg-white p-6 shadow-sm">
        <p className="mb-3 text-sm font-medium text-stone-600">Woche auswählen</p>

        <div className="mb-6 grid grid-cols-2 gap-3">
          {([
            { key: thisWeek, label: 'Diese Woche' },
            { key: nextWeek, label: 'Nächste Woche' },
          ] as const).map(({ key, label }) => (
            <button
              key={key}
              onClick={() => setWeekStart(key)}
              className={`rounded-xl border-2 p-3 text-left transition-colors ${
                weekStart === key
                  ? 'border-emerald-500 bg-emerald-50'
                  : 'border-stone-200 hover:border-stone-300'
              }`}
            >
              <p
                className={`text-sm font-semibold ${
                  weekStart === key ? 'text-emerald-700' : 'text-stone-700'
                }`}
              >
                {label}
              </p>
              <p className="mt-0.5 text-xs text-stone-500">{formatWeek(key)}</p>
            </button>
          ))}
        </div>

        <p className="mb-4 text-sm text-stone-600">
          Der Assistent schlägt dir 10 Gerichte basierend auf den aktuellen Angeboten in deiner
          Region vor. Du wählst aus und weist jedem Gericht einen Wochentag zu.
        </p>

        <div className="mb-4">
          <label className="mb-1 block text-sm font-medium text-stone-600" htmlFor="wish-text">
            Wünsche für diese Woche (optional)
          </label>
          <textarea
            id="wish-text"
            value={wishText}
            onChange={(e) => setWishText(e.target.value.slice(0, 500))}
            maxLength={500}
            rows={3}
            placeholder="z.B. einmal Lasagne, wir haben noch Kartoffeln und eine Zucchini übrig…"
            className="w-full resize-none rounded-lg border border-stone-300 px-3 py-2 text-sm focus:border-emerald-400 focus:outline-none"
          />
          <p className="mt-1 text-xs text-stone-400">
            Wird bei den Vorschlägen berücksichtigt. {wishText.length}/500
          </p>
        </div>

        <div className="mb-4">
          <label className="mb-1 block text-sm font-medium text-stone-600" htmlFor="portion-override">
            Personen diese Woche (optional)
          </label>
          <input
            id="portion-override"
            type="number"
            inputMode="numeric"
            min={2}
            max={20}
            value={portionOverride}
            onChange={(e) => setPortionOverride(e.target.value)}
            placeholder="z.B. 6 bei Gästen"
            className="w-full rounded-lg border border-stone-300 px-3 py-2 text-sm focus:border-emerald-400 focus:outline-none"
          />
          <p className="mt-1 text-xs text-stone-400">
            Standard: dein Profil. Nur für diese eine Woche (z.B. Besuch).
          </p>
        </div>

        {error && <p className="mb-3 rounded bg-red-50 p-3 text-sm text-red-700">{error}</p>}

        {preparedPlanId !== null && (
          <div className="mb-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
            Für diese Woche sind bereits fertige Vorschläge vorbereitet — dein Wunsch bzw. deine
            abweichende Personenzahl konnte dabei noch nicht berücksichtigt werden.
            <button
              onClick={() => navigate(`/plan/${preparedPlanId}`)}
              className="mt-2 block w-full rounded-lg bg-amber-600 py-2 text-center text-xs font-semibold text-white hover:bg-amber-700"
            >
              Trotzdem fortfahren
            </button>
          </div>
        )}

        <button
          onClick={handleStart}
          disabled={loading}
          className="w-full rounded-lg bg-emerald-600 py-3 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
        >
          {loading ? 'Wird gestartet…' : 'Vorschläge generieren'}
        </button>
      </div>
    </main>
  )
}
