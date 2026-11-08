const brl = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' })
const usd = new Intl.NumberFormat('pt-BR', {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 2,
  maximumFractionDigits: 4,
})

export function formatMoney(cents: number): string {
  return brl.format(cents / 100)
}

/** '+R$ 10,00' for money in, '−R$ 10,00' for money out (a real minus sign). */
export function formatSignedMoney(cents: number): string {
  const sign = cents > 0 ? '+' : cents < 0 ? '−' : ''
  return `${sign}${brl.format(Math.abs(cents) / 100)}`
}

export function formatUsd(value: number): string {
  return usd.format(value)
}

export function formatPercent(fraction: number): string {
  return `${Math.round(fraction * 100)}%`
}

function monthDate(month: string): Date {
  const [year, number] = month.split('-').map(Number)
  return new Date(year, number - 1, 1)
}

/** '2026-10' -> 'Outubro de 2026' */
export function formatMonth(month: string): string {
  const text = monthDate(month).toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' })
  return text.charAt(0).toUpperCase() + text.slice(1)
}

/** '2026-10' -> 'out' */
export function formatShortMonth(month: string): string {
  return monthDate(month).toLocaleDateString('pt-BR', { month: 'short' }).replace('.', '')
}

/** '2026-10-05' -> '05/10' */
export function formatDayMonth(isoDate: string): string {
  const [, month, day] = isoDate.split('-')
  return `${day}/${month}`
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' })
}

/** The current month as 'AAAA-MM', in the user's time zone. */
export function currentMonth(today = new Date()): string {
  return `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}`
}
