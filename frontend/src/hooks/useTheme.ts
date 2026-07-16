import { useEffect, useState } from 'react'

// Theme preference: 'system' follows the OS, 'light'/'dark' are manual
// overrides. The resolved value lands as data-theme="light|dark" on <html>
// (initially set by the pre-paint script in index.html) — CSS tokens and
// Tailwind `dark:` variants both key off that attribute.
export type ThemeMode = 'system' | 'light' | 'dark'

const STORAGE_KEY = 'aristeus-theme'

const THEME_COLORS = { light: '#F6F1E7', dark: '#1D1A14' } as const

function resolve(mode: ThemeMode): 'light' | 'dark' {
  if (mode === 'system') {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  }
  return mode
}

function apply(mode: ThemeMode) {
  const resolved = resolve(mode)
  document.documentElement.dataset.theme = resolved
  // Keep the browser-chrome color in sync with the override (both meta tags
  // get the same value, so their media attributes stop mattering).
  document.querySelectorAll('meta[name="theme-color"]').forEach((m) => {
    m.setAttribute('content', THEME_COLORS[resolved])
  })
}

export function useTheme(): [ThemeMode, (mode: ThemeMode) => void] {
  const [mode, setMode] = useState<ThemeMode>(() => {
    const stored = localStorage.getItem(STORAGE_KEY)
    return stored === 'light' || stored === 'dark' ? stored : 'system'
  })

  useEffect(() => {
    apply(mode)
    localStorage.setItem(STORAGE_KEY, mode)
    if (mode !== 'system') return
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = () => apply('system')
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [mode])

  return [mode, setMode]
}
