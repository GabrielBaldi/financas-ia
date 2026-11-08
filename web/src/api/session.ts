import { useSyncExternalStore } from 'react'

// The bearer token lives in localStorage so a page reload keeps the user signed in.
const STORAGE_KEY = 'financas.token'
const listeners = new Set<() => void>()

export function getToken(): string | null {
  return localStorage.getItem(STORAGE_KEY)
}

export function setToken(token: string | null): void {
  if (token) localStorage.setItem(STORAGE_KEY, token)
  else localStorage.removeItem(STORAGE_KEY)
  listeners.forEach((notify) => notify())
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function useToken(): string | null {
  return useSyncExternalStore(subscribe, getToken)
}
