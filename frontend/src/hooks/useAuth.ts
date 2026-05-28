import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react'
import { createElement } from 'react'
import { apiFetch } from '../api/client'

export type Household = {
  id: number
  username: string
  email: string
  is_admin: boolean
  has_profile: boolean
  onboarding_complete: boolean
}

type AuthState = {
  household: Household | null
  loading: boolean
  refresh: () => Promise<void>
}

export const AuthContext = createContext<AuthState>({
  household: null,
  loading: true,
  refresh: async () => {},
})

export function AuthProvider({ children }: { children: ReactNode }) {
  const [household, setHousehold] = useState<Household | null>(null)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    try {
      const h = await apiFetch<Household>('/me')
      setHousehold(h)
    } catch {
      setHousehold(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  return createElement(AuthContext.Provider, { value: { household, loading, refresh } }, children)
}

export const useAuth = () => useContext(AuthContext)
