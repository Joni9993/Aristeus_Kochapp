// Shared recipe body (Zutaten/Zubereitung/Tipps) — used by the recipe
// accordion in Plan.tsx and the cookbook detail view in Cookbook.tsx.
// `zutatenAction`, if given (Plan.tsx passes the Kochmodus button), renders
// right-aligned in the "Zutaten" heading row so it's visible without
// scrolling as soon as the accordion opens.
import type { ReactNode } from 'react'
import type { Recipe } from '../types'

export default function RecipeDetails({
  recipe,
  zutatenAction,
}: {
  recipe: Recipe
  zutatenAction?: ReactNode
}) {
  return (
    <>
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="font-display font-semibold text-ink">Zutaten</h3>
        {zutatenAction && <div className="shrink-0">{zutatenAction}</div>}
      </div>
      <ul className="mb-4 space-y-1">
        {recipe.zutaten.map((ing, i) => (
          <li key={i} className="flex flex-wrap items-center gap-x-2 gap-y-1 text-ink/80">
            {ing.menge && <span className="shrink-0 font-medium">{ing.menge} {ing.einheit}</span>}
            <span className="min-w-0">{ing.name}</span>
            {ing.ist_angebot && (
              <span className="shrink-0 rounded bg-honey-soft px-1 text-xs font-medium text-ink">Angebot</span>
            )}
          </li>
        ))}
      </ul>

      <h3 className="mb-2 font-display font-semibold text-ink">Zubereitung</h3>
      <ol className="mb-4 space-y-1 list-decimal list-inside">
        {recipe.schritte.map((step, i) => (
          <li key={i} className="text-ink/80 leading-relaxed">{step}</li>
        ))}
      </ol>

      {recipe.tipps.length > 0 && (
        <>
          <h3 className="mb-2 font-display font-semibold text-ink">Tipps</h3>
          <ul className="space-y-1">
            {recipe.tipps.map((tip, i) => (
              <li key={i} className="text-muted">💡 {tip}</li>
            ))}
          </ul>
        </>
      )}
    </>
  )
}
