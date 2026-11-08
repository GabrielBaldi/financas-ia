import { useState, type FormEvent } from 'react'
import { DEMO_CREDENTIALS, login, register } from '../api/auth'
import { AiStatus } from '../components/AiStatus'

const STEPS = [
  ['Suas regras', 'o que você já ensinou'],
  ['Regras padrão', 'iFood, Uber, Pix, farmácia…'],
  ['IA', 'só para o que sobrou'],
  ['A revisar', 'a palavra final é sua'],
]

export function LoginPage() {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const isLogin = mode === 'login'

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setPending(true)
    try {
      await (isLogin ? login(email, password) : register(email, password))
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Não foi possível entrar.')
      setPending(false)
    }
  }

  function useDemo() {
    setMode('login')
    setEmail(DEMO_CREDENTIALS.email)
    setPassword(DEMO_CREDENTIALS.password)
  }

  return (
    <div className="login">
      <section className="login__intro" aria-labelledby="pitch">
        <p className="wordmark">
          Finanças <span>com IA</span>
        </p>
        <h1 id="pitch" className="login__title">
          Seu extrato, <em>categorizado</em>.
        </h1>
        <p className="login__lead">
          Importe o OFX ou o CSV do banco. Regras resolvem o óbvio, a IA entra só no que sobra e
          você revisa o resto.
        </p>
        <ol className="steps">
          {STEPS.map(([title, detail]) => (
            <li key={title}>
              <strong>{title}</strong> <span>{detail}</span>
            </li>
          ))}
        </ol>
      </section>

      <section className="card login__card" aria-labelledby="form-title">
        <h2 id="form-title">{isLogin ? 'Entrar' : 'Criar conta'}</h2>
        <form onSubmit={submit} className="form">
          <label className="field">
            <span>E-mail</span>
            <input
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </label>
          <label className="field">
            <span>Senha{!isLogin && ' (mínimo de 8 caracteres)'}</span>
            <input
              type="password"
              autoComplete={isLogin ? 'current-password' : 'new-password'}
              minLength={isLogin ? undefined : 8}
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          <button type="submit" className="button" disabled={pending}>
            {pending ? 'Aguarde…' : isLogin ? 'Entrar' : 'Criar conta e entrar'}
          </button>
        </form>

        <div className="demo">
          <p>
            <strong>Conta de demonstração</strong>
            <br />
            {DEMO_CREDENTIALS.email} · senha {DEMO_CREDENTIALS.password}
          </p>
          <button type="button" className="button button--quiet" onClick={useDemo}>
            Preencher
          </button>
        </div>

        <p className="login__switch">
          {isLogin ? 'Ainda não tem conta?' : 'Já tem conta?'}{' '}
          <button
            type="button"
            className="link-button"
            onClick={() => setMode(isLogin ? 'register' : 'login')}
          >
            {isLogin ? 'Criar conta' : 'Entrar'}
          </button>
        </p>
        <AiStatus />
      </section>
    </div>
  )
}
