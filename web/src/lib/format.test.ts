import { describe, expect, it } from 'vitest'
import { errorMessage } from '../api/client'
import {
  currentMonth,
  formatDayMonth,
  formatMoney,
  formatMonth,
  formatPercent,
  formatShortMonth,
  formatSignedMoney,
} from './format'

// Intl separates the currency symbol with a no-break space; compare with plain spaces.
const plain = (text: string) => text.replace(/\s/g, ' ')

describe('money', () => {
  it('formats cents as reais', () => {
    expect(plain(formatMoney(123456))).toBe('R$ 1.234,56')
  })

  it('shows the direction of the money with a sign', () => {
    expect(plain(formatSignedMoney(-4590))).toBe('−R$ 45,90')
    expect(plain(formatSignedMoney(650000))).toBe('+R$ 6.500,00')
    expect(plain(formatSignedMoney(0))).toBe('R$ 0,00')
  })

  it('rounds confidence to a whole percentage', () => {
    expect(formatPercent(0.916)).toBe('92%')
  })
})

describe('dates', () => {
  it('names months in Portuguese', () => {
    expect(formatMonth('2026-10')).toBe('Outubro de 2026')
    expect(formatShortMonth('2026-02')).toBe('fev')
  })

  it('shows day and month of an ISO date', () => {
    expect(formatDayMonth('2026-10-05')).toBe('05/10')
  })

  it('pads the current month', () => {
    expect(currentMonth(new Date(2026, 0, 15))).toBe('2026-01')
  })
})

describe('API errors', () => {
  it('uses the message the API sent', () => {
    expect(errorMessage(400, { detail: 'Formato não reconhecido.' })).toBe(
      'Formato não reconhecido.',
    )
  })

  it('summarizes validation errors and server failures', () => {
    expect(errorMessage(422, { detail: [{ loc: ['body', 'email'] }] })).toBe(
      'Confira os campos preenchidos.',
    )
    expect(errorMessage(502, null)).toMatch(/servidor/)
  })
})
