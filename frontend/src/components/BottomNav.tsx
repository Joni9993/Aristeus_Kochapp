import { useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { apiFetch } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import { useDarkMode } from '../hooks/useDarkMode'

export default function BottomNav() {
  const { household, refresh } = useAuth()
  const navigate = useNavigate()
  const [showOptions, setShowOptions] = useState(false)
  const { dark, toggle: toggleDark } = useDarkMode()

  async function handleLogout() {
    setShowOptions(false)
    await apiFetch('/auth/logout', { method: 'POST' })
    await refresh()
    navigate('/login', { replace: true })
  }

  const base = 'flex flex-1 flex-col items-center gap-0.5 py-2 text-xs transition-colors'
  const on = 'text-emerald-600'
  const off = 'text-stone-400'

  return (
    <>
      <nav
        className="fixed bottom-0 left-0 right-0 z-30 flex border-t border-stone-200 bg-white"
        style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
      >
        <NavLink to="/" end className={({ isActive }) => `${base} ${isActive ? on : off}`}>
          <HomeIcon />
          <span>Start</span>
        </NavLink>

        <NavLink to="/profile" className={({ isActive }) => `${base} ${isActive ? on : off}`}>
          <PersonIcon />
          <span>Profil</span>
        </NavLink>

        {household?.is_admin && (
          <NavLink to="/admin" className={({ isActive }) => `${base} ${isActive ? on : off}`}>
            <CogIcon />
            <span>Admin</span>
          </NavLink>
        )}

        <button
          onClick={() => setShowOptions(true)}
          className={`${base} ${showOptions ? on : off}`}
        >
          <DotsIcon />
          <span>Mehr</span>
        </button>
      </nav>

      {showOptions && (
        <>
          <div
            className="fixed inset-0 z-40 bg-black/30"
            onClick={() => setShowOptions(false)}
          />
          <div
            className="fixed bottom-0 left-0 right-0 z-50 rounded-t-2xl bg-white px-4 pt-5"
            style={{ paddingBottom: 'max(1.5rem, env(safe-area-inset-bottom))' }}
          >
            <div className="mx-auto mb-5 h-1 w-10 rounded-full bg-stone-200" />
            <p className="mb-4 text-center text-xs font-semibold uppercase tracking-wide text-stone-400">
              Optionen
            </p>

            {/* Dark mode toggle */}
            <div className="mb-3 flex items-center justify-between rounded-xl bg-stone-100 px-4 py-3.5">
              <span className="text-sm font-medium text-stone-800">Dunkles Design</span>
              <button
                type="button"
                onClick={toggleDark}
                className={`relative h-7 w-12 shrink-0 overflow-hidden rounded-full transition-colors duration-200 ${dark ? 'bg-emerald-600' : 'bg-stone-300'}`}
                aria-label="Dunkles Design umschalten"
              >
                <span
                  className={`toggle-knob absolute top-1 h-5 w-5 rounded-full bg-white shadow transition-all duration-200 ${dark ? 'left-6' : 'left-1'}`}
                />
              </button>
            </div>

            <button
              onClick={handleLogout}
              className="w-full rounded-xl border border-red-200 py-3.5 text-sm font-medium text-red-600 active:bg-red-50"
            >
              Abmelden
            </button>
            <button
              onClick={() => setShowOptions(false)}
              className="mt-2.5 mb-1 w-full rounded-xl bg-stone-100 py-3.5 text-sm font-medium text-stone-600 active:bg-stone-200"
            >
              Schließen
            </button>
          </div>
        </>
      )}
    </>
  )
}

function HomeIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="h-6 w-6">
      <path strokeLinecap="round" strokeLinejoin="round" d="m2.25 12 8.954-8.955c.44-.439 1.152-.439 1.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75M8.25 21h8.25" />
    </svg>
  )
}

function PersonIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="h-6 w-6">
      <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0ZM4.501 20.118a7.5 7.5 0 0 1 14.998 0A17.933 17.933 0 0 1 12 21.75c-2.676 0-5.216-.584-7.499-1.632Z" />
    </svg>
  )
}

function CogIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="h-6 w-6">
      <path strokeLinecap="round" strokeLinejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.325.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 0 1 1.37.49l1.296 2.247a1.125 1.125 0 0 1-.26 1.431l-1.003.827c-.293.241-.438.613-.43.992a7.723 7.723 0 0 1 0 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.955.26 1.43l-1.298 2.247a1.125 1.125 0 0 1-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 0 1-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.94-1.11.94h-2.594c-.55 0-1.019-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 0 1-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 0 1-1.369-.49l-1.297-2.247a1.125 1.125 0 0 1 .26-1.431l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 0 1 0-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 0 1-.26-1.43l1.297-2.247a1.125 1.125 0 0 1 1.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.28Z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />
    </svg>
  )
}

function DotsIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="h-6 w-6">
      <path strokeLinecap="round" strokeLinejoin="round" d="M6.75 12a.75.75 0 1 1-1.5 0 .75.75 0 0 1 1.5 0ZM12.75 12a.75.75 0 1 1-1.5 0 .75.75 0 0 1 1.5 0ZM18.75 12a.75.75 0 1 1-1.5 0 .75.75 0 0 1 1.5 0Z" />
    </svg>
  )
}
