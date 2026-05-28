import { Link } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { apiFetch } from '../api/client'
import { useNavigate } from 'react-router-dom'

export default function Home() {
  const { household, refresh } = useAuth()
  const navigate = useNavigate()

  async function handleLogout() {
    await apiFetch('/auth/logout', { method: 'POST' })
    await refresh()
    navigate('/login', { replace: true })
  }

  return (
    <main className="mx-auto max-w-xl p-6">
      <header className="mb-8 flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Aristeus Kochapp</h1>
        <div className="flex items-center gap-3">
          {household?.is_admin && (
            <Link to="/admin" className="text-sm text-stone-500 underline hover:text-stone-700">
              Admin
            </Link>
          )}
          <Link to="/profile" className="text-sm text-stone-500 underline hover:text-stone-700">
            Profil
          </Link>
          <button
            onClick={handleLogout}
            className="text-sm text-stone-500 underline hover:text-stone-700"
          >
            Abmelden
          </button>
        </div>
      </header>

      <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-6 text-center">
        <p className="text-lg font-medium text-emerald-800">
          Willkommen, {household?.username}!
        </p>
        <p className="mt-2 text-sm text-emerald-700">
          Phase 4 bringt den Wochenplan-Flow hierher.
        </p>
        <p className="mt-1 text-xs text-emerald-600">
          Aktuell: Phase 1 abgeschlossen — Auth & Onboarding
        </p>
      </div>

      <div className="mt-6 rounded-xl border border-stone-200 p-4 text-sm text-stone-600">
        <p className="font-medium text-stone-700">Kommt in den nächsten Phasen:</p>
        <ul className="mt-2 list-inside list-disc space-y-1 text-stone-500">
          <li>Phase 2: Kaufda-Integration (Angebote aus deiner Region)</li>
          <li>Phase 3: AI-Harness (Gerichtsvorschläge via OpenRouter)</li>
          <li>Phase 4: Wochenplan-Flow (Vorschläge → Auswahl → Rezepte → Einkaufsliste)</li>
          <li>Phase 5: Feedback & Lernfunktion</li>
        </ul>
      </div>
    </main>
  )
}
