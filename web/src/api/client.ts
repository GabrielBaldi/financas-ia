import { getToken, setToken } from './session'

const API_URL = (import.meta.env.VITE_API_URL ?? 'http://localhost:8102').replace(/\/+$/, '')

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

/** Turns FastAPI's `detail` (a message or a list of validation errors) into one sentence. */
export function errorMessage(status: number, body: unknown): string {
  const detail = (body as { detail?: unknown } | null)?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return 'Confira os campos preenchidos.'
  if (status >= 500) return 'O servidor teve um problema. Tente de novo em instantes.'
  return `Erro inesperado (${status}).`
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE'
  json?: unknown
  body?: FormData | URLSearchParams
}

export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers = new Headers()
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (options.json !== undefined) headers.set('Content-Type', 'application/json')

  let response: Response
  try {
    response = await fetch(`${API_URL}${path}`, {
      method: options.method ?? 'GET',
      headers,
      body: options.json !== undefined ? JSON.stringify(options.json) : options.body,
    })
  } catch {
    throw new ApiError(0, 'Não foi possível falar com a API. Ela está rodando?')
  }

  if (response.status === 401 && token) setToken(null) // expired session: back to the login
  if (response.status === 204) return undefined as T

  const body: unknown = await response.json().catch(() => null)
  if (!response.ok) throw new ApiError(response.status, errorMessage(response.status, body))
  return body as T
}
