// Photo/screenshot recipe import — the "📷 Per Foto" mode of the "Rezept
// hinzufügen" dialog in Cookbook.tsx (see AddRecipeDialog there for the
// url/manual siblings this mirrors in style).
//
// Standalone by design: the Cookbook.tsx rewrite that adds the third mode
// tile is being done in a parallel batch, so this component is meant to be
// dropped straight into that tile once it lands — see the props contract
// below. Usage once wired in:
//
//   {mode === 'photo' && (
//     <PhotoRecipeImport onImported={onAdded} onCancel={() => setMode('url')} />
//   )}
//
// POST /api/recipes/import-photo is multipart/form-data, which apiFetch
// (src/api/client.ts) doesn't support — it always JSON.stringifies the body.
// importPhotos() below reuses apiFetch's exact base-URL/credentials/error
// conventions via a direct fetch call so callers see the same ApiError shape.

import { useEffect, useRef, useState } from 'react'
import { ApiError } from '../api/client'
import type { CookbookEntry } from '../types'

const MAX_PHOTOS = 4
const MAX_PHOTO_MB = 8

type PhotoRecipeImportProps = {
  onImported: (entry: CookbookEntry) => void
  onCancel: () => void
}

async function importPhotos(files: File[]): Promise<CookbookEntry> {
  const form = new FormData()
  for (const file of files) form.append('files', file)

  const res = await fetch('/api/recipes/import-photo', {
    method: 'POST',
    credentials: 'include',
    body: form,
  })

  if (!res.ok) {
    const data = await res.json().catch(() => ({ detail: res.statusText }))
    throw new ApiError(res.status, (data as { detail?: string }).detail ?? 'Unbekannter Fehler')
  }
  return res.json() as Promise<CookbookEntry>
}

export default function PhotoRecipeImport({ onImported, onCancel }: PhotoRecipeImportProps) {
  const [files, setFiles] = useState<File[]>([])
  const [previews, setPreviews] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const inputRef = useRef<HTMLInputElement | null>(null)

  // Object URLs for the thumbnail grid — regenerated whenever the file list
  // changes, old ones revoked so we don't leak memory across re-selections.
  useEffect(() => {
    const urls = files.map((f) => URL.createObjectURL(f))
    setPreviews(urls)
    return () => urls.forEach((u) => URL.revokeObjectURL(u))
  }, [files])

  function addFiles(list: FileList | null) {
    if (!list || list.length === 0) return
    const incoming = Array.from(list)
    const accepted: File[] = []
    let rejected = false
    for (const f of incoming) {
      if (!f.type.startsWith('image/') || f.size > MAX_PHOTO_MB * 1024 * 1024) {
        rejected = true
        continue
      }
      accepted.push(f)
    }
    setError(rejected ? `Nur Fotos bis ${MAX_PHOTO_MB} MB werden unterstützt.` : '')
    setFiles((prev) => [...prev, ...accepted].slice(0, MAX_PHOTOS))
  }

  function removeFile(index: number) {
    setFiles((prev) => prev.filter((_, i) => i !== index))
  }

  async function submit() {
    if (files.length === 0) return
    setLoading(true)
    setError('')
    try {
      const entry = await importPhotos(files)
      onImported(entry)
    } catch (err) {
      if (err instanceof ApiError) {
        setError(
          err.status === 503
            ? 'Gerade überlastet — bitte gleich nochmal versuchen.'
            : err.message,
        )
      } else {
        setError('Fotos konnten nicht analysiert werden.')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-3">
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        multiple
        capture="environment"
        onChange={(e) => {
          addFiles(e.target.files)
          e.target.value = ''
        }}
        className="hidden"
      />

      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        disabled={files.length >= MAX_PHOTOS || loading}
        className="min-h-11 w-full rounded-2xl border border-dashed border-line px-3 py-4 text-sm text-ink/75 hover:bg-surface disabled:opacity-50"
      >
        {files.length === 0
          ? '📷 Fotos auswählen (Kamera oder Galerie)'
          : `+ Weiteres Foto (${files.length}/${MAX_PHOTOS})`}
      </button>

      {previews.length > 0 && (
        <div className="grid grid-cols-4 gap-2">
          {previews.map((src, i) => (
            <div
              key={i}
              className="relative aspect-square min-w-0 overflow-hidden rounded-xl border border-line bg-surface"
            >
              <img src={src} alt={`Foto ${i + 1}`} className="h-full w-full object-cover" />
              <button
                type="button"
                onClick={() => removeFile(i)}
                aria-label="Foto entfernen"
                disabled={loading}
                className="absolute right-1 top-1 flex h-6 w-6 items-center justify-center rounded-full bg-black/60 text-xs leading-none text-white hover:bg-black/80 disabled:opacity-50"
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}

      <p className="text-xs text-muted">
        Kochbuchseite, Screenshot eines Rezept-Posts oder handschriftliche Notiz — bis zu{' '}
        {MAX_PHOTOS} Fotos, max. {MAX_PHOTO_MB} MB pro Foto. Die Fotos werden nur zur Erkennung
        genutzt und nicht gespeichert.
      </p>

      {error && (
        <p className="rounded bg-red-50 dark:bg-red-950/40 p-2 text-xs text-red-700 dark:text-red-300">
          {error}
        </p>
      )}

      <div className="flex gap-2">
        <button
          type="button"
          onClick={onCancel}
          disabled={loading}
          className="min-h-11 rounded-lg border border-line px-3 py-2.5 text-sm text-muted hover:bg-surface disabled:opacity-50"
        >
          Abbrechen
        </button>
        <button
          type="button"
          onClick={submit}
          disabled={loading || files.length === 0}
          className="flex min-h-11 flex-1 items-center justify-center gap-2 rounded-lg bg-olive py-2.5 text-sm font-medium text-olive-on hover:bg-olive-hover disabled:opacity-50"
        >
          {loading && (
            <span className="h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-olive-on border-t-transparent" />
          )}
          {loading ? 'Fotos werden analysiert…' : 'Rezept erkennen'}
        </button>
      </div>
    </div>
  )
}
