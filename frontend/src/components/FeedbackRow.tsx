import { useState } from 'react'
import { apiFetch } from '../api/client'
import type { Dish } from '../types'

export default function FeedbackRow({
  planId,
  dish,
  onThumbsChange,
}: {
  planId: number
  dish: Dish
  onThumbsChange?: (dishId: number, thumbs: number) => void
}) {
  const [thumbs, setThumbs] = useState<number | null>(dish.feedback_thumbs)
  const [portion, setPortion] = useState<string | null>(dish.feedback_portion_note)
  const [fav, setFav] = useState(dish.is_favorite)
  const [freeText, setFreeText] = useState(dish.feedback_free_text ?? '')
  const [saving, setSaving] = useState(false)
  const [textSaved, setTextSaved] = useState(false)

  async function sendPatch(patch: Record<string, unknown>) {
    try {
      await apiFetch(`/plans/${planId}/dishes/${dish.id}/feedback`, {
        method: 'PATCH',
        body: patch,
      })
    } catch {
      //
    }
  }

  async function handleThumbs(t: number) {
    setThumbs(t)
    await sendPatch({ thumbs: t })
    onThumbsChange?.(dish.id, t)
  }

  async function handlePortion(opt: string) {
    const next = portion === opt ? '' : opt
    setPortion(next || null)
    await sendPatch({ portion_note: next })
  }

  async function handleFav() {
    const next = !fav
    setFav(next)
    await sendPatch({ is_favorite: next })
  }

  async function saveText() {
    setSaving(true)
    setTextSaved(false)
    await sendPatch({ free_text: freeText })
    setSaving(false)
    setTextSaved(true)
    setTimeout(() => setTextSaved(false), 2000)
  }

  return (
    <div className="mt-4 space-y-3 border-t border-line pt-3">
      <div className="flex items-center gap-3">
        <span className="shrink-0 text-xs text-muted">Wie war's?</span>
        <button
          onClick={() => handleThumbs(1)}
          className={`min-h-11 min-w-11 rounded-full px-3 py-2 text-sm ${thumbs === 1 ? 'bg-olive text-olive-on' : 'bg-olive-soft text-ink hover:bg-line'}`}
        >
          👍
        </button>
        <button
          onClick={() => handleThumbs(-1)}
          className={`min-h-11 min-w-11 rounded-full px-3 py-2 text-sm ${thumbs === -1 ? 'bg-red-500 text-white' : 'bg-olive-soft text-ink hover:bg-line'}`}
        >
          👎
        </button>
        <button
          onClick={handleFav}
          className={`ml-auto shrink-0 p-2 text-lg leading-none ${fav ? 'text-honey' : 'text-muted hover:text-honey/70'}`}
          title={fav ? 'Aus Favoriten entfernen' : 'Als Favorit merken'}
        >
          {fav ? '★' : '☆'}
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <span className="shrink-0 text-xs text-muted">Portion:</span>
        {(['zu wenig', 'genau richtig', 'zu viel'] as const).map((opt) => (
          <button
            key={opt}
            onClick={() => handlePortion(opt)}
            className={`min-h-9 rounded-full px-2.5 py-1.5 text-xs ${portion === opt ? 'bg-olive text-olive-on' : 'bg-olive-soft text-ink hover:bg-line'}`}
          >
            {opt}
          </button>
        ))}
      </div>

      <div className="flex gap-2">
        <textarea
          value={freeText}
          onChange={(e) => setFreeText(e.target.value)}
          placeholder="Notiz (optional)…"
          rows={2}
          className="min-w-0 flex-1 resize-none rounded-lg border border-line p-2 text-sm focus:border-olive focus:outline-none"
        />
        <button
          onClick={saveText}
          disabled={saving}
          className="shrink-0 self-end rounded-lg bg-olive-soft px-3 py-2 text-xs text-ink hover:bg-line disabled:opacity-50"
        >
          {saving ? '…' : textSaved ? '✓' : 'Speichern'}
        </button>
      </div>
    </div>
  )
}
