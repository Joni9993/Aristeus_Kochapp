import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiFetch, ApiError } from '../api/client'

function nextMonday(): string {
  const d = new Date()
  const day = d.getDay() // 0=Sun, 1=Mon, ...
  const daysToMonday = day === 1 ? 0 : (8 - day) % 7 || 7
  d.setDate(d.getDate() + daysToMonday)
  return d.toISOString().slice(0, 10)
}

function formatWeek(iso: string): string {
  const d = new Date(iso + 'T00:00:00')
  const sun = new Date(d)
  sun.setDate(d.getDate() + 6)
  return `${d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' })} – ${sun.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' })}`
}

export default function PlanNew() {
  const navigate = useNavigate()
  const [weekStart] = useState(nextMonday)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleStart() {
    setLoading(true)
    setError('')
    try {
      const resp = await apiFetch<{ id: number }>('/plans', {
        method: 'POST',
        body: JSON.stringify({ week_start_date: weekStart }),
      })
      navigate(`/plan/${resp.id}`)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Fehler beim Erstellen des Plans')
      setLoading(false)
    }
  }

  return (
    <main className="mx-auto max-w-xl p-6">
      <button onClick={() => navigate('/')} className="mb-4 text-sm text-stone-500 underline hover:text-stone-700">
        Zurück
      </button>

      <h1 className="mb-6 text-2xl font-semibold tracking-tight">Neue Woche planen</h1>

      <div className="rounded-xl border border-stone-200 bg-white p-6 shadow-sm">
        <p className="mb-1 text-sm text-stone-500">Woche</p>
        <p className="mb-6 text-xl font-semibold text-stone-800">{formatWeek(weekStart)}</p>

        <p className="mb-4 text-sm text-stone-600">
          Der Assistent schlägt dir 10 Gerichte basierend auf den aktuellen Angeboten in deiner Region vor.
          Du wählst aus und weist jedem Gericht einen Wochentag zu.
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
