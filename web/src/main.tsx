import '@fontsource-variable/fraunces/wght.css'
import '@fontsource-variable/fraunces/wght-italic.css'
import './styles.css'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { HashRouter } from 'react-router'
import { ApiError } from './api/client'
import { App } from './App'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Retrying a 4xx (expired session, bad filter) only delays the error message.
      retry: (failures, error) =>
        !(error instanceof ApiError && error.status < 500) && failures < 2,
      refetchOnWindowFocus: false,
    },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      {/* Hash URLs work on any static host (GitHub Pages included) without rewrite rules. */}
      <HashRouter>
        <App />
      </HashRouter>
    </QueryClientProvider>
  </StrictMode>,
)
