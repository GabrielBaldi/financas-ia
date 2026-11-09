import type { AiProvider, ImportSummary, Meta } from '../api/types'
import { formatUsd } from './format'

const PROVIDER_LABELS: Record<AiProvider, string> = {
  anthropic: 'Anthropic',
  nvidia: 'NVIDIA',
}

/** 'IA ligada · NVIDIA (minimaxai/minimax-m3.1-flash)' or 'IA desligada · só regras'. */
export function aiStatusLabel({
  ai_enabled,
  ai_provider,
  ai_model,
}: Pick<Meta, 'ai_enabled' | 'ai_provider' | 'ai_model'>): string {
  if (!ai_enabled) return 'IA desligada · só regras'
  if (!ai_provider) return 'IA ligada'
  const provider = PROVIDER_LABELS[ai_provider]
  return ai_model ? `IA ligada · ${provider} (${ai_model})` : `IA ligada · ${provider}`
}

/**
 * The recorded cost of an import. Tokens spent with no cost mean the provider has no price
 * configured (NVIDIA), which is not the same as free: shown as a dash, not as US$ 0,00.
 */
export function aiCostLabel({
  ai_input_tokens,
  ai_output_tokens,
  ai_cost_usd,
}: Pick<ImportSummary, 'ai_input_tokens' | 'ai_output_tokens' | 'ai_cost_usd'>): string {
  const spentTokens = ai_input_tokens + ai_output_tokens > 0
  return spentTokens && ai_cost_usd === 0 ? '—' : formatUsd(ai_cost_usd)
}
