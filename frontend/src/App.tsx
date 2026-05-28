import { useEffect, useState } from 'react'

type HealthResponse = {
  status: string
  service: string
  version: string
  env: string
  time: string
}

export default function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/health')
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json() as Promise<HealthResponse>
      })
      .then(setHealth)
      .catch((e) => setError(e.message))
  }, [])

  return (
    <main className="mx-auto flex min-h-full max-w-xl flex-col gap-6 p-6">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">Aristeus Kochapp</h1>
        <p className="mt-1 text-sm text-stone-500">
          Wochenplanung aus regionalen Angeboten. Phase 0 — Hello World.
        </p>
      </header>

      <section className="rounded-xl border border-stone-200 bg-white p-4 shadow-sm">
        <h2 className="text-sm font-medium uppercase tracking-wide text-stone-500">
          Backend-Verbindung
        </h2>
        {error && (
          <p className="mt-2 text-sm text-red-600">
            Backend nicht erreichbar: <code>{error}</code>
          </p>
        )}
        {!error && !health && <p className="mt-2 text-sm text-stone-500">Lade…</p>}
        {health && (
          <dl className="mt-2 grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm">
            <dt className="text-stone-500">Status</dt>
            <dd className="font-medium text-emerald-700">{health.status}</dd>
            <dt className="text-stone-500">Service</dt>
            <dd>{health.service}</dd>
            <dt className="text-stone-500">Version</dt>
            <dd>{health.version}</dd>
            <dt className="text-stone-500">Env</dt>
            <dd>{health.env}</dd>
            <dt className="text-stone-500">Zeit</dt>
            <dd className="font-mono text-xs">{health.time}</dd>
          </dl>
        )}
      </section>

      <footer className="text-xs text-stone-400">
        Folgende Phasen: Auth → Kaufda → AI-Harness → Wochenplan-Flow
      </footer>
    </main>
  )
}
