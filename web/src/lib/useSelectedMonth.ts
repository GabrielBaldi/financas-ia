import { useSearchParams } from 'react-router'
import { useMonths } from '../api/hooks'
import { currentMonth } from './format'

/** The month in the URL (?mes=AAAA-MM), or the newest month that has data. */
export function useSelectedMonth() {
  const months = useMonths()
  const [params, setParams] = useSearchParams()
  const month = params.get('mes') ?? months.data?.[0] ?? currentMonth()

  function setMonth(next: string) {
    setParams(
      (current) => {
        current.set('mes', next)
        return current
      },
      { replace: true },
    )
  }

  return { month, setMonth, months: months.data ?? [], isLoading: months.isLoading }
}
