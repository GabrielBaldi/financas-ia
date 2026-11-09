/** Whole seconds left until `expiresAt` (an ISO date), never below zero. */
export function secondsLeft(expiresAt: string, now: number): number {
  return Math.max(0, Math.ceil((Date.parse(expiresAt) - now) / 1000))
}

/** 599 -> '9:59' */
export function formatCountdown(seconds: number): string {
  const minutes = Math.floor(seconds / 60)
  return `${minutes}:${String(seconds % 60).padStart(2, '0')}`
}

/** The import screen's line about Telegram entries found in the statement. */
export function reconciledMessage(count: number): string {
  return count === 1
    ? '1 lançamento do Telegram conferido com o extrato'
    : `${count} lançamentos do Telegram conferidos com o extrato`
}

/** What to send to the bot. */
export function connectCommand(code: string): string {
  return `/conectar ${code}`
}
