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
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleStart() {
    setLoading(true)
    setError('')
    try {
      const resp = await apiFetch<{ id: number }>('/plans', {
        method: 'POST',
        body: { week_start_date: weekStart },
      })
      navigate(`/plan/${resp.id}`)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Fehler beim Erstellen des Plans')
      setLoading(false)
    }
  }

  return (
    <main className="mx-auto max-w-xl p-6">
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

        {error && <p className="mb-3 rounded bg-red-50 p-3 text-sm text-red-700">{error}</p>}

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
