import { useQueryClient } from '@tanstack/react-query'
import { NavLink, Outlet } from 'react-router'
import { logout } from '../api/auth'
import { AiStatus } from './AiStatus'

const LINKS = [
  { to: '/revisao', label: 'Revisão' },
  { to: '/painel', label: 'Painel' },
  { to: '/importar', label: 'Importar' },
  { to: '/regras', label: 'Regras' },
]

function focusMain() {
  document.getElementById('conteudo')?.focus()
}

export function Layout() {
  const queryClient = useQueryClient()

  async function signOut() {
    await logout().catch(() => undefined) // signing out locally is enough if the API is down
    queryClient.clear()
  }

  return (
    <div className="shell">
      {/* A button, not an #anchor: the hash is used by the router. */}
      <button type="button" className="skip-link button" onClick={focusMain}>
        Pular para o conteúdo
      </button>
      <header className="masthead">
        <p className="wordmark">
          Finanças <span>com IA</span>
        </p>
        <nav aria-label="Principal" className="nav">
          {LINKS.map(({ to, label }) => (
            <NavLink key={to} to={to} className="nav__link">
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="masthead__side">
          <AiStatus />
          <button type="button" className="button button--quiet" onClick={signOut}>
            Sair
          </button>
        </div>
      </header>
      <main id="conteudo" tabIndex={-1} className="page">
        <Outlet />
      </main>
      <footer className="footer">
        Projeto de portfólio · os dados da conta demo são fictícios.
      </footer>
    </div>
  )
}
