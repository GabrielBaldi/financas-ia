// Mirrors the API schemas (api/src/financas/schemas.py). Money is always integer cents.

export type Category =
  | 'alimentacao'
  | 'mercado'
  | 'transporte'
  | 'moradia'
  | 'contas'
  | 'saude'
  | 'educacao'
  | 'lazer'
  | 'assinaturas'
  | 'compras'
  | 'transferencias'
  | 'taxas'
  | 'fatura'
  | 'investimentos'
  | 'receitas'
  | 'outros'

export type Source = 'user_rule' | 'keyword' | 'ai' | 'manual' | 'review'

export interface Token {
  access_token: string
  token_type: 'bearer'
  expires_at: string
}

export interface Meta {
  ai_enabled: boolean
  ai_model: string | null
  categories: { slug: Category; label: string }[]
}

export interface Transaction {
  id: number
  account_id: number
  date: string
  description: string
  amount_cents: number
  category: Category | null
  categorized_by: Source
  confidence: number | null
  suggested_category: Category | null
}

export interface TransactionPage {
  items: Transaction[]
  total: number
}

export interface Similar {
  pattern: string
  count: number
}

export interface Rule {
  id: number
  pattern: string
  category: Category
  created_at: string
}

export interface RuleCreated {
  rule: Rule
  applied: number
}

export interface ImportSummary {
  id: number
  filename: string
  file_format: string
  account: { id: number; name: string }
  created_at: string
  total_rows: number
  inserted: number
  duplicates: number
  by_user_rule: number
  by_keyword: number
  by_ai: number
  to_review: number
  ai_input_tokens: number
  ai_output_tokens: number
  ai_cost_usd: number
}

export interface MonthTotal {
  month: string
  expenses_cents: number
  income_cents: number
}

export interface Dashboard {
  month: string
  expenses_cents: number
  income_cents: number
  by_category: { category: Category | null; total_cents: number }[]
  monthly: MonthTotal[]
}
