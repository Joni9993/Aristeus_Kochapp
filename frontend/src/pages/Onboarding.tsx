import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiFetch, ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'

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

const ALLERGIES = ['Gluten', 'Laktose', 'Nüsse', 'Erdnüsse', 'Soja', 'Eier', 'Schalentiere']

type ProfileData = {
  postal_code: string
  adults: number
  kids: number
  diet: string
  allergies: string[]
  allowed_meats: string[]
  max_cook_time_min: number
  preferred_cuisines: string[]
  no_gos: string[]
  budget_sensitivity: number
  selected_stores: string[]
  monday_only_offers: boolean
}

const INITIAL: ProfileData = {
  postal_code: '',
  adults: 2,
  kids: 0,
  diet: 'omnivore',
  allergies: [],
  allowed_meats: ['chicken', 'turkey', 'beef', 'pork', 'fish'],
  max_cook_time_min: 50,
  preferred_cuisines: [],
  no_gos: [],
  budget_sensitivity: 3,
  selected_stores: ['rewe', 'lidl', 'aldi', 'edeka', 'penny', 'netto', 'kaufland'],
  monday_only_offers: true,
}

export default function Onboarding() {
  const navigate = useNavigate()
  const { household, refresh } = useAuth()
  const [step, setStep] = useState(1)
  const [data, setData] = useState<ProfileData>(INITIAL)
  const [noGoInput, setNoGoInput] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (household?.onboarding_complete) navigate('/', { replace: true })
  }, [household, navigate])

  function toggle<T extends string>(list: T[], item: T): T[] {
    return list.includes(item) ? list.filter((x) => x !== item) : [...list, item]
  }

  async function finish() {
    setSaving(true)
    setError('')
    try {
      await apiFetch('/me/profile', { method: 'PUT', body: data })
      await apiFetch('/me/onboarding/complete', { method: 'POST' })
      await refresh()
      navigate('/', { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Fehler beim Speichern')
      setSaving(false)
    }
  }

  const TOTAL = 6

  return (
    <main className="mx-auto flex min-h-screen max-w-lg flex-col px-4 py-5 sm:p-6">
      <header className="mb-8">
        <p className="text-sm text-stone-500">
          Schritt {step} von {TOTAL}
        </p>
        <div className="mt-2 flex gap-1">
          {Array.from({ length: TOTAL }, (_, i) => (
            <div
              key={i}
              className={`h-1.5 flex-1 rounded-full ${i < step ? 'bg-emerald-500' : 'bg-stone-200'}`}
            />
          ))}
        </div>
      </header>

      {step === 1 && (
        <Step title="Wo wohnst du?">
          <label className="mb-1 block text-sm font-medium text-stone-700">Postleitzahl</label>
          <input
            className="w-full rounded-lg border border-stone-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
            value={data.postal_code}
            onChange={(e) => setData({ ...data, postal_code: e.target.value })}
            placeholder="z.B. 80331"
            maxLength={10}
            inputMode="numeric"
          />
        </Step>
      )}

      {step === 2 && (
        <Step title="Dein Haushalt">
          <Counter
            label="Erwachsene"
            value={data.adults}
            min={1}
            max={10}
            onChange={(v) => setData({ ...data, adults: v })}
          />
          <Counter
            label="Kinder"
            value={data.kids}
            min={0}
            max={10}
            onChange={(v) => setData({ ...data, kids: v })}
          />
        </Step>
      )}

      {step === 3 && (
        <Step title="Ernährungsweise">
          <div className="space-y-2">
            {[
              { id: 'omnivore', label: 'Alles (Fleisch, Fisch, vegetarisch)' },
              { id: 'flexitarian', label: 'Flexitarisch (wenig Fleisch)' },
              { id: 'vegetarian', label: 'Vegetarisch' },
              { id: 'vegan', label: 'Vegan' },
            ].map((opt) => (
              <label key={opt.id} className="flex cursor-pointer items-center gap-3">
                <input
                  type="radio"
                  name="diet"
                  value={opt.id}
                  checked={data.diet === opt.id}
                  onChange={() =>
                    setData({
                      ...data,
                      diet: opt.id,
                      allowed_meats:
                        opt.id === 'vegan' || opt.id === 'vegetarian' ? [] : data.allowed_meats,
                    })
                  }
                  className="accent-emerald-600"
                />
                <span className="text-sm">{opt.label}</span>
              </label>
            ))}
          </div>
          <div className="mt-6">
            <p className="mb-2 text-sm font-medium text-stone-700">Allergien / Unverträglichkeiten</p>
            <div className="flex flex-wrap gap-2">
              {ALLERGIES.map((a) => (
                <Chip
                  key={a}
                  label={a}
                  active={data.allergies.includes(a)}
                  onClick={() => setData({ ...data, allergies: toggle(data.allergies, a) })}
                />
              ))}
            </div>
          </div>
        </Step>
      )}

      {step === 4 && (
        <Step title="Fleisch & Fisch">
          {data.diet === 'vegan' || data.diet === 'vegetarian' ? (
            <p className="text-sm text-stone-500">
              Nicht relevant für deine Ernährungsweise.
            </p>
          ) : (
            <>
              <p className="mb-3 text-sm text-stone-600">
                Welche Fleisch- und Fischsorten sollen im Wochenplan vorkommen?
              </p>
              <div className="flex flex-wrap gap-2">
                {MEATS.map((m) => (
                  <Chip
                    key={m.id}
                    label={m.label}
                    active={data.allowed_meats.includes(m.id)}
                    onClick={() =>
                      setData({ ...data, allowed_meats: toggle(data.allowed_meats, m.id) })
                    }
                  />
                ))}
              </div>
            </>
          )}
        </Step>
      )}

      {step === 5 && (
        <Step title="Kochzeit & Vorlieben">
          <div className="mb-6">
            <label className="mb-1 block text-sm font-medium text-stone-700">
              Maximale Kochzeit: <strong>{data.max_cook_time_min} Min</strong>
            </label>
            <input
              type="range"
              min={10}
              max={120}
              step={5}
              value={data.max_cook_time_min}
              onChange={(e) => setData({ ...data, max_cook_time_min: Number(e.target.value) })}
              className="w-full accent-emerald-600"
            />
            <div className="flex justify-between text-xs text-stone-400">
              <span>10 Min</span>
              <span>120 Min</span>
            </div>
          </div>
          <div className="mb-6">
            <p className="mb-2 text-sm font-medium text-stone-700">
              Angebots-Orientierung:{' '}
              <strong>
                {['', 'Gering', 'Etwas', 'Mittel', 'Stark', 'Maximal'][data.budget_sensitivity]}
              </strong>
            </p>
            <input
              type="range"
              min={1}
              max={5}
              value={data.budget_sensitivity}
              onChange={(e) => setData({ ...data, budget_sensitivity: Number(e.target.value) })}
              className="w-full accent-emerald-600"
            />
            <div className="flex justify-between text-xs text-stone-400">
              <span>Gering</span>
              <span>Maximal</span>
            </div>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-stone-700">
              No-Gos (Zutaten / Gerichte, die du nicht magst)
            </label>
            <div className="flex gap-2">
              <input
                className="flex-1 rounded-lg border border-stone-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                value={noGoInput}
                onChange={(e) => setNoGoInput(e.target.value)}
                placeholder="z.B. Pilze"
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && noGoInput.trim()) {
                    e.preventDefault()
                    setData({ ...data, no_gos: [...data.no_gos, noGoInput.trim()] })
                    setNoGoInput('')
                  }
                }}
              />
              <button
                type="button"
                className="rounded-lg border border-stone-300 px-3 py-2 text-sm hover:bg-stone-100"
                onClick={() => {
                  if (noGoInput.trim()) {
                    setData({ ...data, no_gos: [...data.no_gos, noGoInput.trim()] })
                    setNoGoInput('')
                  }
                }}
              >
                +
              </button>
            </div>
            <div className="mt-2 flex flex-wrap gap-2">
              {data.no_gos.map((ng) => (
                <Chip
                  key={ng}
                  label={ng}
                  active
                  onClick={() =>
                    setData({ ...data, no_gos: data.no_gos.filter((x) => x !== ng) })
                  }
                />
              ))}
            </div>
          </div>
        </Step>
      )}

      {step === 6 && (
        <Step title="Läden & Einkaufsplan">
          <div className="mb-6">
            <p className="mb-2 text-sm font-medium text-stone-700">Welche Läden nutzt du?</p>
            <div className="flex flex-wrap gap-2">
              {STORES.map((s) => (
                <Chip
                  key={s.id}
                  label={s.label}
                  active={data.selected_stores.includes(s.id)}
                  onClick={() =>
                    setData({ ...data, selected_stores: toggle(data.selected_stores, s.id) })
                  }
                />
              ))}
            </div>
          </div>
          <div className="rounded-xl border border-stone-200 bg-stone-50 p-4">
            <p className="mb-3 text-sm font-medium text-stone-700">Wie oft gehst du einkaufen?</p>
            <div className="space-y-3">
              <label className="flex cursor-pointer items-start gap-3">
                <input
                  type="radio"
                  name="mondayOnly"
                  checked={data.monday_only_offers}
                  onChange={() => setData({ ...data, monday_only_offers: true })}
                  className="mt-0.5 accent-emerald-600"
                />
                <div>
                  <p className="text-sm font-medium">Einmal pro Woche (Montag)</p>
                  <p className="text-xs text-stone-500">
                    Nur Angebote, die ab Montag gelten. Praktisch für einen einzigen Einkauf.
                  </p>
                </div>
              </label>
              <label className="flex cursor-pointer items-start gap-3">
                <input
                  type="radio"
                  name="mondayOnly"
                  checked={!data.monday_only_offers}
                  onChange={() => setData({ ...data, monday_only_offers: false })}
                  className="mt-0.5 accent-emerald-600"
                />
                <div>
                  <p className="text-sm font-medium">Mehrmals pro Woche</p>
                  <p className="text-xs text-stone-500">
                    Alle Angebote, auch wenn sie erst Mi. oder Fr. starten.
                  </p>
                </div>
              </label>
            </div>
          </div>
        </Step>
      )}

      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

      <div className="mt-auto flex gap-3 pt-8">
        {step > 1 && (
          <button
            onClick={() => setStep(step - 1)}
            className="flex-1 rounded-lg border border-stone-300 px-4 py-2 text-sm hover:bg-stone-100"
          >
            Zurück
          </button>
        )}
        {step < TOTAL ? (
          <button
            onClick={() => setStep(step + 1)}
            className="flex-1 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700"
          >
            Weiter
          </button>
        ) : (
          <button
            onClick={finish}
            disabled={saving || data.selected_stores.length === 0}
            className="flex-1 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            {saving ? 'Speichern…' : 'Fertig – App starten'}
          </button>
        )}
      </div>
    </main>
  )
}

function Step({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex-1">
      <h2 className="mb-6 text-xl font-semibold">{title}</h2>
      <div className="space-y-4">{children}</div>
    </div>
  )
}

function Counter({
  label,
  value,
  min,
  max,
  onChange,
}: {
  label: string
  value: number
  min: number
  max: number
  onChange: (v: number) => void
}) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-sm font-medium text-stone-700">{label}</span>
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => onChange(Math.max(min, value - 1))}
          className="flex h-8 w-8 items-center justify-center rounded-full border border-stone-300 text-lg hover:bg-stone-100"
        >
          −
        </button>
        <span className="w-6 text-center text-sm font-semibold">{value}</span>
        <button
          type="button"
          onClick={() => onChange(Math.min(max, value + 1))}
          className="flex h-8 w-8 items-center justify-center rounded-full border border-stone-300 text-lg hover:bg-stone-100"
        >
          +
        </button>
      </div>
    </div>
  )
}

function Chip({
  label,
  active,
  onClick,
}: {
  label: string
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-full px-3 py-1 text-sm transition-colors ${
        active
          ? 'bg-emerald-600 text-white'
          : 'border border-stone-300 text-stone-700 hover:bg-stone-100'
      }`}
    >
      {active ? `✓ ${label}` : label}
    </button>
  )
}
