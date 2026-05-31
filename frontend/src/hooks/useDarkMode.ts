import { useEffect, useState } from 'react'

function readPref(): boolean {
  try {
    const stored = localStorage.getItem('darkMode')
    if (stored !== null) return stored === 'true'
    return window.matchMedia('(prefers-color-scheme: dark)').matches
  } catch {
    return false
  }
}

export function useDarkMode() {
  const [dark, setDark] = useState<boolean>(readPref)

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
    try { localStorage.setItem('darkMode', String(dark)) } catch {}
  }, [dark])

  return { dark, toggle: () => setDark(d => !d) }
}
