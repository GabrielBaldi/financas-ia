import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './client'
import type {
  Category,
  Dashboard,
  ImportSummary,
  Meta,
  Rule,
  RuleCreated,
  Similar,
  Transaction,
  TransactionPage,
} from './types'

export interface TransactionFilters {
  month: string
  category: Category | ''
  toReview: boolean
}

export function useMeta() {
  return useQuery({ queryKey: ['meta'], queryFn: () => api<Meta>('/meta'), staleTime: Infinity })
}

export function useMonths() {
  return useQuery({ queryKey: ['months'], queryFn: () => api<string[]>('/transactions/months') })
}

export function useTransactions({ month, category, toReview }: TransactionFilters) {
  const params = new URLSearchParams({ month, limit: '500' })
  if (category) params.set('category', category)
  if (toReview) params.set('to_review', 'true')
  return useQuery({
    queryKey: ['transactions', month, category, toReview],
    queryFn: () => api<TransactionPage>(`/transactions?${params}`),
    enabled: Boolean(month),
  })
}

export function useDashboard(month: string) {
  return useQuery({
    queryKey: ['dashboard', month],
    queryFn: () => api<Dashboard>(`/dashboard?month=${month}`),
    enabled: Boolean(month),
  })
}

export function useImports() {
  return useQuery({ queryKey: ['imports'], queryFn: () => api<ImportSummary[]>('/imports') })
}

export function useRules() {
  return useQuery({ queryKey: ['rules'], queryFn: () => api<Rule[]>('/rules') })
}

/** Anything that changes categories makes every list and chart stale. */
function useInvalidateData() {
  const queryClient = useQueryClient()
  return () =>
    Promise.all(
      ['transactions', 'months', 'dashboard', 'imports', 'rules'].map((key) =>
        queryClient.invalidateQueries({ queryKey: [key] }),
      ),
    )
}

export function useSetCategory() {
  const invalidate = useInvalidateData()
  return useMutation({
    mutationFn: ({ id, category }: { id: number; category: Category }) =>
      api<Transaction>(`/transactions/${id}`, { method: 'PATCH', json: { category } }),
    onSuccess: invalidate,
  })
}

export function fetchSimilar(transactionId: number) {
  return api<Similar>(`/transactions/${transactionId}/similar`)
}

export function useCreateRule() {
  const invalidate = useInvalidateData()
  return useMutation({
    mutationFn: (rule: { pattern: string; category: Category }) =>
      api<RuleCreated>('/rules', { method: 'POST', json: rule }),
    onSuccess: invalidate,
  })
}

export function useDeleteRule() {
  const invalidate = useInvalidateData()
  return useMutation({
    mutationFn: (id: number) => api<void>(`/rules/${id}`, { method: 'DELETE' }),
    onSuccess: invalidate,
  })
}

export function useImportStatement() {
  const invalidate = useInvalidateData()
  return useMutation({
    mutationFn: ({ file, accountName }: { file: File; accountName: string }) => {
      const form = new FormData()
      form.set('file', file)
      form.set('account_name', accountName)
      return api<ImportSummary>('/imports', { method: 'POST', body: form })
    },
    onSuccess: invalidate,
  })
}
