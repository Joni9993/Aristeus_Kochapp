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

// One entry in "Unser Kochbuch" (GET /api/recipes) — a deduped confirmed
// dish with its stored recipe, from any past plan.
export type CookbookEntry = {
  dish_id: number
  plan_id: number
  name: string
  cuisine: string | null
  cook_time_min: number | null
  is_favorite: boolean
  image_url: string | null
  week_start_date: string | null
  recipe: Recipe | null
}

export const DAYS = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag']

/** Maps 0=Sonntag..6=Samstag (JS Date#getDay) to the German weekday name used in DAYS. */
export function germanWeekdayName(d: Date): string {
  const day = d.getDay()
  return DAYS[day === 0 ? 6 : day - 1]
}

const CUISINE_COLORS: Record<string, string> = {
  vegetarisch: 'bg-emerald-100 text-emerald-700',
  vegan: 'bg-green-100 text-green-700',
  Fisch: 'bg-blue-100 text-blue-700',
  Fleisch: 'bg-amber-100 text-amber-700',
  gemischt: 'bg-stone-100 text-stone-600',
}

export function cuisineBadgeClass(cuisine: string | null): string {
  return CUISINE_COLORS[cuisine || 'gemischt'] || 'bg-stone-100 text-stone-600'
}
