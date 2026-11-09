import { describe, expect, it } from 'vitest'
import { aiCostLabel, aiStatusLabel } from './ai'

// Intl separates the currency symbol with a no-break space; compare with plain spaces.
const plain = (text: string) => text.replace(/\s/g, ' ')

describe('AI status', () => {
  it('names the provider and the model', () => {
    expect(
      aiStatusLabel({
        ai_enabled: true,
        ai_provider: 'nvidia',
        ai_model: 'minimaxai/minimax-m3.1-flash',
      }),
    ).toBe('IA ligada · NVIDIA (minimaxai/minimax-m3.1-flash)')
    expect(
      aiStatusLabel({ ai_enabled: true, ai_provider: 'anthropic', ai_model: 'claude-haiku-5-5' }),
    ).toBe('IA ligada · Anthropic (claude-haiku-5-5)')
  })

  it('still says the AI is on when the API does not name it', () => {
    expect(aiStatusLabel({ ai_enabled: true, ai_provider: null, ai_model: null })).toBe('IA ligada')
    expect(aiStatusLabel({ ai_enabled: true, ai_provider: 'nvidia', ai_model: null })).toBe(
      'IA ligada · NVIDIA',
    )
  })

  it('says when only the rules run', () => {
    expect(aiStatusLabel({ ai_enabled: false, ai_provider: null, ai_model: null })).toBe(
      'IA desligada · só regras',
    )
  })
})

describe('AI cost of an import', () => {
  it('shows the estimated cost in dollars', () => {
    expect(
      plain(aiCostLabel({ ai_input_tokens: 2000, ai_output_tokens: 400, ai_cost_usd: 0.0004 })),
    ).toBe('US$ 0,0004')
  })

  it('shows zero when the AI was not needed', () => {
    expect(plain(aiCostLabel({ ai_input_tokens: 0, ai_output_tokens: 0, ai_cost_usd: 0 }))).toBe(
      'US$ 0,00',
    )
  })

  it('shows a dash when tokens were spent with no price configured', () => {
    expect(aiCostLabel({ ai_input_tokens: 2000, ai_output_tokens: 400, ai_cost_usd: 0 })).toBe('—')
  })
})
