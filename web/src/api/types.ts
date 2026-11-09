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

/** 'telegram': typed in the bot and not yet found in an imported statement. */
export type Origin = 'import' | 'telegram'

export interface Token {
  access_token: string
  token_type: 'bearer'
  expires_at: string
}

/** Which AI categorizes what the rules cannot (api/src/financas/config.py). */
export type AiProvider = 'anthropic' | 'nvidia'

export interface Meta {
  ai_enabled: boolean
  /** null when the AI is off. */
  ai_provider: AiProvider | null
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
  origin: Origin
  /** The user's own words from Telegram, on a statement row that absorbed the entry. */
  note: string | null
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

export interface Account {
  id: number
  name: string
}

export interface ImportSummary {
  id: number
  filename: string
  file_format: string
  account: Account
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
  /** Telegram entries merged into rows of this statement. */
  reconciled: number
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

export interface TelegramStatus {
  linked: boolean
  linked_at: string | null
  /** null: entries go to "Lançamentos manuais". */
  default_account: Account | null
}

export interface PairingCode {
  code: string
  expires_at: string
}
