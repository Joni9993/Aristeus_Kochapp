// Shared recipe body (Zutaten/Zubereitung/Tipps) — used by the recipe
// accordion in Plan.tsx and the cookbook detail view in Cookbook.tsx.
import type { Recipe } from '../types'

export default function RecipeDetails({ recipe }: { recipe: Recipe }) {
  return (
    <>
      <h3 className="mb-2 font-semibold text-stone-700">Zutaten</h3>
      <ul className="mb-4 space-y-1">
        {recipe.zutaten.map((ing, i) => (
          <li key={i} className="flex gap-2 text-stone-600">
            {ing.menge && <span className="font-medium">{ing.menge} {ing.einheit}</span>}
            <span>{ing.name}</span>
            {ing.ist_angebot && (
              <span className="rounded bg-emerald-100 px-1 text-xs text-emerald-700">Angebot</span>
            )}
          </li>
        ))}
      </ul>

      <h3 className="mb-2 font-semibold text-stone-700">Zubereitung</h3>
      <ol className="mb-4 space-y-1 list-decimal list-inside">
        {recipe.schritte.map((step, i) => (
          <li key={i} className="text-stone-600 leading-relaxed">{step}</li>
        ))}
      </ol>

      {recipe.tipps.length > 0 && (
        <>
          <h3 className="mb-2 font-semibold text-stone-700">Tipps</h3>
          <ul className="space-y-1">
            {recipe.tipps.map((tip, i) => (
              <li key={i} className="text-stone-500">💡 {tip}</li>
            ))}
          </ul>
        </>
      )}
    </>
  )
}
