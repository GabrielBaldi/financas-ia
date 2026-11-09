import { describe, expect, it } from 'vitest'
import { connectCommand, formatCountdown, reconciledMessage, secondsLeft } from './telegram'

describe('pairing code countdown', () => {
  const expiresAt = '2026-11-08T15:10:00Z'
  const at = (iso: string) => Date.parse(iso)

  it('counts whole seconds left, rounding up', () => {
    expect(secondsLeft(expiresAt, at('2026-11-08T15:00:00Z'))).toBe(600)
    expect(secondsLeft(expiresAt, at('2026-11-08T15:09:59.200Z'))).toBe(1)
  })

  it('never goes below zero', () => {
    expect(secondsLeft(expiresAt, at('2026-11-08T15:30:00Z'))).toBe(0)
  })

  it('shows minutes and padded seconds', () => {
    expect(formatCountdown(600)).toBe('10:00')
    expect(formatCountdown(599)).toBe('9:59')
    expect(formatCountdown(5)).toBe('0:05')
  })

  it('builds the command to send to the bot', () => {
    expect(connectCommand('048213')).toBe('/conectar 048213')
  })
})

describe('reconciliation message', () => {
  it('agrees in number', () => {
    expect(reconciledMessage(1)).toBe('1 lançamento do Telegram conferido com o extrato')
    expect(reconciledMessage(3)).toBe('3 lançamentos do Telegram conferidos com o extrato')
  })
})
