import type { SelectHTMLAttributes } from 'react'
import { useMeta } from '../api/hooks'
import type { Category } from '../api/types'
import { formatMonth } from '../lib/format'

type SelectProps = Omit<SelectHTMLAttributes<HTMLSelectElement>, 'value' | 'onChange'>

interface CategorySelectProps extends SelectProps {
  value: Category | ''
  onChange: (category: Category | '') => void
  /** Text of the empty option, e.g. "Todas" in a filter or "A revisar" in a row. */
  emptyLabel?: string
  emptyDisabled?: boolean
}

export function CategorySelect({
  value,
  onChange,
  emptyLabel,
  emptyDisabled = false,
  ...rest
}: CategorySelectProps) {
  const { data } = useMeta()
  return (
    <select {...rest} value={value} onChange={(event) => onChange(event.target.value as Category)}>
      {emptyLabel !== undefined && (
        <option value="" disabled={emptyDisabled}>
          {emptyLabel}
        </option>
      )}
      {data?.categories.map(({ slug, label }) => (
        <option key={slug} value={slug}>
          {label}
        </option>
      ))}
    </select>
  )
}

interface MonthSelectProps extends SelectProps {
  months: string[]
  value: string
  onChange: (month: string) => void
}

export function MonthSelect({ months, value, onChange, ...rest }: MonthSelectProps) {
  // The selected month may have no data yet (e.g. the current one): keep it selectable.
  const options = months.includes(value) ? months : [value, ...months]
  return (
    <select {...rest} value={value} onChange={(event) => onChange(event.target.value)}>
      {options.map((month) => (
        <option key={month} value={month}>
          {formatMonth(month)}
        </option>
      ))}
    </select>
  )
}
