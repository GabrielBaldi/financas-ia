import { api } from './client'
import { setToken } from './session'
import type { Token } from './types'

export const DEMO_CREDENTIALS = { email: 'demo@example.com', password: 'demo1234' }

export async function login(email: string, password: string): Promise<void> {
  // OAuth2 password flow: the API expects a form with `username` and `password`.
  const form = new URLSearchParams({ username: email, password })
  const token = await api<Token>('/auth/token', { method: 'POST', body: form })
  setToken(token.access_token)
}

export async function register(email: string, password: string): Promise<void> {
  await api('/auth/register', { method: 'POST', json: { email, password } })
  await login(email, password)
}

export async function logout(): Promise<void> {
  try {
    await api('/auth/logout', { method: 'POST' })
  } finally {
    setToken(null)
  }
}
