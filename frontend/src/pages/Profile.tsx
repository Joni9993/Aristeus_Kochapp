import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiFetch, ApiError } from '../api/client'

const STORES = [
  { id: 'rewe', label: 'Rewe' },
  { id: 'lidl', label: 'Lidl' },
  { id: 'aldi', label: 'Aldi' },
  { id: 'edeka', label: 'Edeka' },
  { id: 'penny', label: 'Penny' },
  { id: 'netto', label: 'Netto' },
  { id: 'kaufland', label: 'Kaufland' },
]

const MEATS = [
  { id: 'chicken', label: 'Huhn' },
  { id: 'turkey', label: 'Pute' },
  { id: 'beef', label: 'Rind' },
  { id: 'pork', label: 'Schwein' },
  { id: 'fish', label: 'Fisch' },
]

type Profile = {
  adults: number; kids: number; diet: string; allergies: string[]
  allowed_meats: string[]; max_cook_time_min: number; preferred_cuisines: string[]
  no_gos: string[]; budget_sensitivity: number; postal_code: string
  selected_stores: string[]; monday_only_offers: boolean; include_desserts: boolean
  onboarding_complete: boolean; updated_at: string
}

export default function Profile() {
  const navigate = useNavigate()
  const [profile, setProfile] = useState<Profile | null>(null)
  const [form, setForm] = useState<Partial<Profile>>({})
  const [noGoInput, setNoGoInput] = useState('')
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [deleting, setDeleting] = useState(false)

  useEffect(() => {
    apiFetch<Profile>('/me/profile').then((p) => { setProfile(p); setForm(p) }).catch(() => {})
  }, [])

  function toggle<T extends string>(list: T[], item: T): T[] {
    return list.includes(item) ? list.filter(x => x !== item) : [...list, item]
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault()
    setError(''); setSaved(false); setLoading(true)
    try {
      const updated = await apiFetch<Profile>('/me/profile', { method: 'PUT', body: form })
      setProfile(updated); setForm(updated); setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Fehler beim Speichern')
    } finally { setLoading(false) }
  }

  function handleExport() {
    const a = document.createElement('a')
    a.href = '/api/me/export'
    a.download = ''
    a.click()
  }

  async function handleDelete() {
    if (!confirm('Konto und alle Daten unwiderruflich löschen?')) return
    if (!confirm('Wirklich? Diese Aktion kann nicht rückgängig gemacht werden.')) return
    setDeleting(true)
    try {
      await apiFetch('/me', { method: 'DELETE' })
      navigate('/login', { replace: true })
    } catch {
      setDeleting(false)
    }
  }

  if (!profile) return (
    <div className="flex min-h-screen items-center justify-center text-muted">Laden…</div>
  )

  const f = form as Profile

  return (
    <main className="mx-auto max-w-xl px-4 py-6">
      <h1 className="mb-6 border-b border-honey/30 pb-4 font-display text-xl font-semibold text-ink">Profil</h1>

      <form onSubmit={handleSave} className="space-y-4">

        {/* Adresse */}
        <Card title="Adresse">
          <Row label="Postleitzahl">
            <input
              className="w-36 rounded-xl border border-line px-3 py-2.5 focus:outline-none focus:ring-2 focus:ring-olive"
              value={f.postal_code ?? ''}
              onChange={e => setForm({ ...f, postal_code: e.target.value })}
              maxLength={10}
              inputMode="numeric"
            />
          </Row>
        </Card>

        {/* Haushalt */}
        <Card title="Haushalt">
          <Counter
            label="Erwachsene"
            value={f.adults ?? 2}
            min={1} max={10}
            onChange={v => setForm({ ...f, adults: v })}
          />
          <div className="border-t border-line" />
          <Counter
            label="Kinder"
            value={f.kids ?? 0}
            min={0} max={10}
            onChange={v => setForm({ ...f, kids: v })}
          />
        </Card>

        {/* Ernährung */}
        <Card title="Ernährung">
          <div className="space-y-1">
            {[
              { id: 'omnivore', label: 'Alles (Fleisch & Fisch)' },
              { id: 'flexitarian', label: 'Flexitarisch (wenig Fleisch)' },
              { id: 'vegetarian', label: 'Vegetarisch' },
              { id: 'vegan', label: 'Vegan' },
            ].map(opt => (
              <label
                key={opt.id}
                className="flex cursor-pointer items-center justify-between rounded-xl px-3 py-3 active:bg-surface"
              >
                <span className="text-sm text-ink">{opt.label}</span>
                <input
                  type="radio"
                  name="diet"
                  value={opt.id}
                  checked={f.diet === opt.id}
                  onChange={() => setForm({
                    ...f,
                    diet: opt.id,
                    allowed_meats: (opt.id === 'vegan' || opt.id === 'vegetarian') ? [] : f.allowed_meats,
                  })}
                  className="h-4 w-4 accent-olive"
                />
              </label>
            ))}
          </div>

          {f.diet !== 'vegan' && f.diet !== 'vegetarian' && (
            <>
              <div className="border-t border-line pt-3">
                <p className="mb-2 px-3 text-xs font-semibold uppercase tracking-wide text-muted">
                  Fleisch &amp; Fisch
                </p>
                <div className="flex flex-wrap gap-2 px-3 pb-1">
                  {MEATS.map(m => (
                    <Chip
                      key={m.id}
                      label={m.label}
                      active={(f.allowed_meats ?? []).includes(m.id)}
                      onClick={() => setForm({ ...f, allowed_meats: toggle(f.allowed_meats ?? [], m.id) })}
                    />
                  ))}
                </div>
              </div>
            </>
          )}
        </Card>

        {/* Kochzeit & Budget */}
        <Card title="Kochzeit &amp; Budget">
          <div className="px-1">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm text-ink">Max. Kochzeit</span>
              <span className="text-sm font-semibold text-ink">{f.max_cook_time_min} Min</span>
            </div>
            <input
              type="range" min={10} max={120} step={5}
              value={f.max_cook_time_min ?? 50}
              onChange={e => setForm({ ...f, max_cook_time_min: Number(e.target.value) })}
              className="w-full accent-olive"
            />
            <div className="flex justify-between text-xs text-muted mt-0.5">
              <span>10 Min</span><span>120 Min</span>
            </div>
          </div>

          <div className="border-t border-line pt-4 px-1">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm text-ink">Angebots-Orientierung</span>
              <span className="text-sm font-semibold text-ink">
                {['', 'Gering', 'Etwas', 'Mittel', 'Stark', 'Maximal'][f.budget_sensitivity ?? 3]}
              </span>
            </div>
            <input
              type="range" min={1} max={5}
              value={f.budget_sensitivity ?? 3}
              onChange={e => setForm({ ...f, budget_sensitivity: Number(e.target.value) })}
              className="w-full accent-olive"
            />
            <div className="flex justify-between text-xs text-muted mt-0.5">
              <span>Gering</span><span>Maximal</span>
            </div>
          </div>
        </Card>

        {/* No-Gos */}
        <Card title="No-Gos">
          <div className="flex gap-2 px-1">
            <input
              className="flex-1 rounded-xl border border-line px-3 py-2.5 focus:outline-none focus:ring-2 focus:ring-olive"
              value={noGoInput}
              onChange={e => setNoGoInput(e.target.value)}
              placeholder="Zutat oder Gericht…"
              onKeyDown={e => {
                if (e.key === 'Enter' && noGoInput.trim()) {
                  e.preventDefault()
                  setForm({ ...f, no_gos: [...(f.no_gos ?? []), noGoInput.trim()] })
                  setNoGoInput('')
                }
              }}
            />
            <button
              type="button"
              className="rounded-xl border border-line px-4 py-2.5 text-lg font-medium active:bg-olive-soft"
              onClick={() => {
                if (noGoInput.trim()) {
                  setForm({ ...f, no_gos: [...(f.no_gos ?? []), noGoInput.trim()] })
                  setNoGoInput('')
                }
              }}
            >
              +
            </button>
          </div>
          {(f.no_gos ?? []).length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2 px-1">
              {(f.no_gos ?? []).map(ng => (
                <Chip key={ng} label={ng} active onClick={() => setForm({ ...f, no_gos: (f.no_gos ?? []).filter(x => x !== ng) })} />
              ))}
            </div>
          )}
        </Card>

        {/* Läden */}
        <Card title="Läden">
          <div className="flex flex-wrap gap-2 px-1">
            {STORES.map(s => (
              <Chip
                key={s.id}
                label={s.label}
                active={(f.selected_stores ?? []).includes(s.id)}
                onClick={() => setForm({ ...f, selected_stores: toggle(f.selected_stores ?? [], s.id) })}
              />
            ))}
          </div>
          <div className="border-t border-line pt-3 space-y-1">
            {[
              { val: true, label: 'Einmal pro Woche (Montag-Angebote)' },
              { val: false, label: 'Mehrmals pro Woche (alle Angebote)' },
            ].map(opt => (
              <label
                key={String(opt.val)}
                className="flex cursor-pointer items-center justify-between rounded-xl px-3 py-3 active:bg-surface"
              >
                <span className="text-sm text-ink">{opt.label}</span>
                <input
                  type="radio"
                  name="mondayOnly"
                  checked={f.monday_only_offers === opt.val}
                  onChange={() => setForm({ ...f, monday_only_offers: opt.val })}
                  className="h-4 w-4 accent-olive"
                />
              </label>
            ))}
          </div>
        </Card>

        {/* Vorschläge */}
        <Card title="Vorschläge">
          <label className="flex cursor-pointer items-center justify-between rounded-xl px-1 py-1 active:bg-surface">
            <div>
              <p className="text-sm font-medium text-ink">Auch Desserts vorschlagen</p>
              <p className="text-xs text-muted mt-0.5">Kuchen, Süßspeisen und Nachspeisen</p>
            </div>
            <div
              className={`relative ml-4 h-7 w-12 shrink-0 overflow-hidden rounded-full transition-colors duration-200 ${f.include_desserts ? 'bg-olive' : 'bg-line'}`}
              onClick={() => setForm({ ...f, include_desserts: !f.include_desserts })}
            >
              <span className={`toggle-knob absolute top-1 h-5 w-5 rounded-full bg-card shadow transition-all duration-200 ${f.include_desserts ? 'left-6' : 'left-1'}`} />
            </div>
          </label>
        </Card>

        {error && <p className="px-1 text-sm text-red-600 dark:text-red-400">{error}</p>}
        {saved && <p className="px-1 text-sm text-olive">✓ Gespeichert</p>}

        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-xl bg-olive py-3.5 text-sm font-semibold text-olive-on active:bg-olive-hover disabled:opacity-50"
        >
          {loading ? 'Speichern…' : 'Profil speichern'}
        </button>
      </form>

      {/* Datenschutz */}
      <div className="mt-8 border-t border-line pt-6 space-y-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted">Datenschutz</p>
        <button
          onClick={handleExport}
          className="w-full rounded-xl border border-line py-3.5 text-sm text-ink active:bg-surface"
        >
          Daten exportieren (JSON)
        </button>
        <button
          onClick={handleDelete}
          disabled={deleting}
          className="w-full rounded-xl border border-red-300 dark:border-red-800 py-3.5 text-sm text-red-600 dark:text-red-400 active:bg-red-50 dark:active:bg-red-950/40 disabled:opacity-50"
        >
          {deleting ? 'Wird gelöscht…' : 'Konto und alle Daten löschen'}
        </button>
      </div>
    </main>
  )
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-line bg-card shadow-sm overflow-hidden">
      <div className="border-b border-line px-4 py-3">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted">{title}</h2>
      </div>
      <div className="px-4 py-3 space-y-3">
        {children}
      </div>
    </div>
  )
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-sm text-ink">{label}</span>
      {children}
    </div>
  )
}

function Counter({ label, value, min, max, onChange }: {
  label: string; value: number; min: number; max: number; onChange: (v: number) => void
}) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-sm text-ink">{label}</span>
      <div className="flex items-center gap-4">
        <button
          type="button"
          onClick={() => onChange(Math.max(min, value - 1))}
          className="flex h-9 w-9 items-center justify-center rounded-full border border-line text-lg active:bg-olive-soft"
        >
          −
        </button>
        <span className="w-6 text-center text-sm font-semibold">{value}</span>
        <button
          type="button"
          onClick={() => onChange(Math.min(max, value + 1))}
          className="flex h-9 w-9 items-center justify-center rounded-full border border-line text-lg active:bg-olive-soft"
        >
          +
        </button>
      </div>
    </div>
  )
}

function Chip({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-full px-3 py-1.5 text-sm transition-colors ${
        active ? 'bg-olive text-olive-on' : 'border border-line text-ink active:bg-olive-soft'
      }`}
    >
      {active ? `✓ ${label}` : label}
    </button>
  )
}
