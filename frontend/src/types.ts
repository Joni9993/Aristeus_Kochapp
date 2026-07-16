// Shared domain types for weekly plans, dishes, recipes and shopping lists.
// Kept in one place so Plan.tsx, Home.tsx, PlanFeedback.tsx and the shared
// FeedbackRow component all agree on the same shapes.

export type Dish = {
  id: number
  name: string
  description: string | null
  cuisine: string | null
  cook_time_min: number | null
  cook_day: string | null
  dish_status: 'suggestion' | 'confirmed' | 'rejected'
  is_favorite: boolean
  feedback_thumbs: number | null
  feedback_portion_note: string | null
  feedback_free_text: string | null
  recipe: Recipe | null
  image_url: string | null
}

export type RecipeIngredient = {
  name: string
  menge: number | null
  einheit: string | null
  ist_angebot: boolean
}

export type Recipe = {
  zutaten: RecipeIngredient[]
  schritte: string[]
  geschaetzte_zeit_min: number
  tipps: string[]
}

export type ShoppingItem = {
  id: number
  ingredient: string
  quantity: string | null
  unit: string | null
  store: string | null
  live_from_date: string | null
  is_checked: boolean
  is_already_have: boolean
  is_angebot: boolean
  price_text: string | null
}

export type Savings = {
  offers_used: number
  offer_total: number
  estimated_savings: number
}

export type Plan = {
  id: number
  week_start_date: string
  status: string
  wish_text: string | null
  portion_override: number | null
  created_at: string
  dishes?: Dish[]
  shopping_items?: ShoppingItem[]
  savings?: Savings
}

// One entry in "Unser Kochbuch" (GET /api/recipes) — a row in saved_recipes,
// either archived from a confirmed plan dish (source: "gekocht") or a
// household's own imported/manual recipe (source: "eigene"). saved_recipe_id
// is always present (favorite/delete always go through /recipes/saved/{id});
// dish_id/plan_id/feedback_thumbs are best-effort enrichment for "gekocht"
// entries (newest confirmed PlanDish with the same name) and are null once
// that plan has been deleted — the frontend just hides the thumbs row then.
export type CookbookEntry = {
  source: 'gekocht' | 'eigene'
  saved_recipe_id: number
  dish_id: number | null
  plan_id: number | null
  name: string
  cuisine: string | null
  cook_time_min: number | null
  is_favorite: boolean
  feedback_thumbs: number | null
  image_url: string | null
  week_start_date: string | null
  recipe: Recipe | null
}

/** Stable identity for a cookbook entry. */
export function cookbookEntryKey(entry: CookbookEntry): string {
  return `saved-${entry.saved_recipe_id}`
}

export const DAYS = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag']

/** Maps 0=Sonntag..6=Samstag (JS Date#getDay) to the German weekday name used in DAYS. */
export function germanWeekdayName(d: Date): string {
  const day = d.getDay()
  return DAYS[day === 0 ? 6 : day - 1]
}

const CUISINE_COLORS: Record<string, string> = {
  vegetarisch: 'bg-olive-soft text-olive',
  vegan: 'bg-lime-100 text-lime-800 dark:bg-lime-900/30 dark:text-lime-300',
  Fisch: 'bg-slate-100 text-slate-600 dark:bg-slate-800/60 dark:text-slate-300',
  Fleisch: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300',
  gemischt: 'bg-line/60 text-muted',
}

export function cuisineBadgeClass(cuisine: string | null): string {
  return CUISINE_COLORS[cuisine || 'gemischt'] || 'bg-line/60 text-muted'
}
