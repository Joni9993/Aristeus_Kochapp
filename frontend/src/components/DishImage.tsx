// Shared dish photo / placeholder — used by the suggestion cards (Plan.tsx),
// the recipe accordion (Plan.tsx) and the cookbook grid (Cookbook.tsx).
// Falls back to a soft gradient + category emoji when no image_url is set
// (e.g. no PEXELS_API_KEY configured, or the lookup found nothing).

const CUISINE_EMOJI: Record<string, string> = {
  vegetarisch: '🥦',
  vegan: '🌱',
  Fisch: '🐟',
  Fleisch: '🍖',
  gemischt: '🍲',
}

export default function DishImage({
  imageUrl,
  name,
  cuisine,
  className = '',
}: {
  imageUrl: string | null
  name: string
  cuisine: string | null
  className?: string
}) {
  if (imageUrl) {
    return (
      <img
        src={imageUrl}
        alt={name}
        className={`w-full object-cover ${className}`}
        loading="lazy"
      />
    )
  }

  const emoji = CUISINE_EMOJI[cuisine || 'gemischt'] || '🍲'
  return (
    <div
      className={`flex w-full items-center justify-center bg-gradient-to-br from-honey-soft to-olive-soft text-3xl ${className || 'h-20'}`}
      aria-hidden="true"
    >
      {emoji}
    </div>
  )
}
