import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
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

  if (!profile) return <div className="flex min-h-screen items-center justify-center text-stone-400">Laden…</div>

  const f = form as Profile

  return (
    <main className="mx-auto max-w-xl p-6">
      <div className="mb-6 flex items-center gap-4">
        <Link to="/" className="text-sm text-stone-500 underline hover:text-stone-700">← Zurück</Link>
        <h1 className="text-xl font-semibold">Profil bearbeiten</h1>
      </div>

      <form onSubmit={handleSave} className="space-y-8">
        <Section title="Adresse">
          <label className="mb-1 block text-sm font-medium text-stone-700">Postleitzahl</label>
          <input className="w-32 rounded-lg border border-stone-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
            value={f.postal_code ?? ''} onChange={e => setForm({ ...f, postal_code: e.target.value })} maxLength={10} />
        </Section>

        <Section title="Haushalt">
          <div className="flex gap-8">
            <Counter label="Erwachsene" value={f.adults ?? 2} min={1} max={10} onChange={v => setForm({ ...f, adults: v })} />
            <Counter label="Kinder" value={f.kids ?? 0} min={0} max={10} onChange={v => setForm({ ...f, kids: v })} />
          </div>
        </Section>

        <Section title="Ernährung">
          <div className="flex flex-wrap gap-2">
            {[['omnivore','Alles'], ['flexitarian','Flexitarisch'], ['vegetarian','Vegetarisch'], ['vegan','Vegan']].map(([id, label]) => (
              <label key={id} className="flex cursor-pointer items-center gap-2">
                <input type="radio" name="diet" value={id} checked={f.diet === id}
                  onChange={() => setForm({ ...f, diet: id, allowed_meats: (id === 'vegan' || id === 'vegetarian') ? [] : f.allowed_meats })}
                  className="accent-emerald-600" />
                <span className="text-sm">{label}</span>
              </label>
            ))}
          </div>
          {f.diet !== 'vegan' && f.diet !== 'vegetarian' && (
            <div className="mt-4">
              <p className="mb-2 text-sm font-medium text-stone-700">Fleisch & Fisch</p>
              <div className="flex flex-wrap gap-2">
                {MEATS.map(m => (
                  <Chip key={m.id} label={m.label} active={(f.allowed_meats ?? []).includes(m.id)}
                    onClick={() => setForm({ ...f, allowed_meats: toggle(f.allowed_meats ?? [], m.id) })} />
                ))}
              </div>
            </div>
          )}
        </Section>

        <Section title="Kochzeit & Budget">
          <label className="mb-1 block text-sm font-medium text-stone-700">
            Max. Kochzeit: <strong>{f.max_cook_time_min} Min</strong>
          </label>
          <input type="range" min={10} max={120} step={5} value={f.max_cook_time_min ?? 50}
            onChange={e => setForm({ ...f, max_cook_time_min: Number(e.target.value) })}
            className="w-full accent-emerald-600" />
          <label className="mt-4 mb-1 block text-sm font-medium text-stone-700">
            Angebots-Orientierung: <strong>{['','Gering','Etwas','Mittel','Stark','Maximal'][f.budget_sensitivity ?? 3]}</strong>
          </label>
          <input type="range" min={1} max={5} value={f.budget_sensitivity ?? 3}
            onChange={e => setForm({ ...f, budget_sensitivity: Number(e.target.value) })}
            className="w-full accent-emerald-600" />
        </Section>

        <Section title="No-Gos">
          <div className="flex gap-2">
            <input className="flex-1 rounded-lg border border-stone-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
              value={noGoInput} onChange={e => setNoGoInput(e.target.value)} placeholder="Zutat / Gericht hinzufügen"
              onKeyDown={e => { if (e.key === 'Enter' && noGoInput.trim()) { e.preventDefault(); setForm({ ...f, no_gos: [...(f.no_gos ?? []), noGoInput.trim()] }); setNoGoInput('') }}} />
            <button type="button" className="rounded-lg border border-stone-300 px-3 py-2 text-sm hover:bg-stone-100"
              onClick={() => { if (noGoInput.trim()) { setForm({ ...f, no_gos: [...(f.no_gos ?? []), noGoInput.trim()] }); setNoGoInput('') }}}>+</button>
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            {(f.no_gos ?? []).map(ng => (
              <Chip key={ng} label={ng} active onClick={() => setForm({ ...f, no_gos: (f.no_gos ?? []).filter(x => x !== ng) })} />
            ))}
          </div>
        </Section>

        <Section title="Läden">
          <div className="flex flex-wrap gap-2">
            {STORES.map(s => (
              <Chip key={s.id} label={s.label} active={(f.selected_stores ?? []).includes(s.id)}
                onClick={() => setForm({ ...f, selected_stores: toggle(f.selected_stores ?? [], s.id) })} />
            ))}
          </div>
          <div className="mt-4 space-y-2">
            {[{ val: true, label: 'Einmal/Woche (nur Mo.-Angebote)' }, { val: false, label: 'Mehrmals/Woche (alle Angebote)' }].map(opt => (
              <label key={String(opt.val)} className="flex cursor-pointer items-center gap-2">
                <input type="radio" name="mondayOnly" checked={f.monday_only_offers === opt.val}
                  onChange={() => setForm({ ...f, monday_only_offers: opt.val })} className="accent-emerald-600" />
                <span className="text-sm">{opt.label}</span>
              </label>
            ))}
          </div>
        </Section>

        <Section title="Vorschläge">
          <label className="flex cursor-pointer items-center gap-3">
            <div className={`relative h-6 w-11 rounded-full transition-colors ${f.include_desserts ? 'bg-emerald-600' : 'bg-stone-300'}`}
              onClick={() => setForm({ ...f, include_desserts: !f.include_desserts })}>
              <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform ${f.include_desserts ? 'translate-x-5' : 'translate-x-0.5'}`} />
            </div>
            <div>
              <span className="text-sm font-medium">Auch Desserts vorschlagen</span>
              <p className="text-xs text-stone-500">Kuchen, Süßspeisen und Nachspeisen in den Wochenplan einbeziehen</p>
            </div>
          </label>
        </Section>

        {error && <p className="text-sm text-red-600">{error}</p>}
        {saved && <p className="text-sm text-emerald-600">Gespeichert!</p>}
        <button type="submit" disabled={loading}
          className="w-full rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50">
          {loading ? 'Speichern…' : 'Profil speichern'}
        </button>
      </form>
      <div className="mt-10 border-t border-stone-200 pt-6">
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-stone-500">Datenschutz</h2>
        <div className="space-y-3">
          <button
            onClick={handleExport}
            className="w-full rounded-lg border border-stone-300 px-4 py-2 text-sm text-stone-700 hover:bg-stone-50"
          >
            Daten exportieren (JSON)
          </button>
          <button
            onClick={handleDelete}
            disabled={deleting}
            className="w-full rounded-lg border border-red-300 px-4 py-2 text-sm text-red-600 hover:bg-red-50 disabled:opacity-50"
          >
            {deleting ? 'Wird gelöscht…' : 'Konto und alle Daten löschen'}
          </button>
        </div>
      </div>
    </main>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-stone-500">{title}</h2>
      <div className="space-y-3">{children}</div>
    </div>
  )
}

function Counter({ label, value, min, max, onChange }: { label: string; value: number; min: number; max: number; onChange: (v: number) => void }) {
  return (
    <div className="flex items-center gap-3">
      <span className="text-sm text-stone-700 w-24">{label}</span>
      <button type="button" onClick={() => onChange(Math.max(min, value - 1))} className="flex h-8 w-8 items-center justify-center rounded-full border border-stone-300 hover:bg-stone-100">−</button>
      <span className="w-5 text-center text-sm font-semibold">{value}</span>
      <button type="button" onClick={() => onChange(Math.min(max, value + 1))} className="flex h-8 w-8 items-center justify-center rounded-full border border-stone-300 hover:bg-stone-100">+</button>
    </div>
  )
}

function Chip({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick}
      className={`rounded-full px-3 py-1 text-sm transition-colors ${active ? 'bg-emerald-600 text-white' : 'border border-stone-300 text-stone-700 hover:bg-stone-100'}`}>
      {active ? `✓ ${label}` : label}
    </button>
  )
}
