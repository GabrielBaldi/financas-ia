import { useState, type CSSProperties } from 'react'
import { Link } from 'react-router'
import { useDashboard } from '../api/hooks'
import type { Dashboard } from '../api/types'
import { MonthSelect } from '../components/Selects'
import { formatMoney, formatMonth, formatShortMonth } from '../lib/format'
import { useCategoryLabel } from '../lib/labels'
import { useSelectedMonth } from '../lib/useSelectedMonth'

export function DashboardPage() {
  const { month, setMonth, months } = useSelectedMonth()
  const dashboard = useDashboard(month)

  return (
    <>
      <header className="page__head page__head--row">
        <div>
          <h1>Painel</h1>
          <p>Para onde foi o dinheiro em {formatMonth(month).toLowerCase()}.</p>
        </div>
        <div className="field field--inline">
          <label htmlFor="dashboard-month">Mês</label>
          <MonthSelect id="dashboard-month" months={months} value={month} onChange={setMonth} />
        </div>
      </header>

      {dashboard.isPending && <p role="status">Carregando painel…</p>}
      {dashboard.isError && (
        <p className="error" role="alert">
          {dashboard.error.message}
        </p>
      )}
      {dashboard.data && <DashboardBody data={dashboard.data} onSelectMonth={setMonth} />}
    </>
  )
}

function DashboardBody({ data, onSelectMonth }: MonthlyChartProps) {
  const balance = data.income_cents - data.expenses_cents
  return (
    <>
      <dl className="figures">
        <div className="figure figure--out">
          <dt>Gastos</dt>
          <dd>{formatMoney(data.expenses_cents)}</dd>
        </div>
        <div className="figure figure--in">
          <dt>Entradas</dt>
          <dd>{formatMoney(data.income_cents)}</dd>
        </div>
        <div className="figure">
          <dt>Saldo do mês</dt>
          <dd>{formatMoney(balance)}</dd>
        </div>
      </dl>

      <div className="dashboard-grid">
        <section className="card" aria-labelledby="by-category">
          <h2 id="by-category">Gastos por categoria</h2>
          <CategoryBars data={data} />
        </section>
        <section className="card" aria-labelledby="by-month">
          <h2 id="by-month">Últimos 6 meses</h2>
          <MonthlyChart data={data} onSelectMonth={onSelectMonth} />
        </section>
      </div>
      <p className="note">
        Pagamento de fatura e investimentos são dinheiro mudando de bolso: não contam como gasto nem
        como entrada.
      </p>
    </>
  )
}

/** Magnitude by category: one hue, sorted, value labels in text color. Also a real table. */
function CategoryBars({ data }: { data: Dashboard }) {
  const label = useCategoryLabel()
  if (data.by_category.length === 0) {
    return <p className="empty">Nenhum gasto neste mês.</p>
  }
  const largest = data.by_category[0].total_cents
  return (
    <table className="bars">
      <thead className="visually-hidden">
        <tr>
          <th scope="col">Categoria</th>
          <th scope="col">Total</th>
          <th scope="col">Parte dos gastos</th>
        </tr>
      </thead>
      <tbody>
        {data.by_category.map(({ category, total_cents }) => {
          const filter = category === null ? 'revisar=1' : `categoria=${category}`
          const ratio = { '--ratio': total_cents / largest } as CSSProperties
          return (
            <tr key={category ?? 'review'} className={category === null ? 'bars__row--review' : ''}>
              <th scope="row">
                <Link to={`/revisao?mes=${data.month}&${filter}`}>{label(category)}</Link>
              </th>
              <td className="bars__value">{formatMoney(total_cents)}</td>
              <td className="bars__cell">
                <span className="bars__track">
                  <span className="bars__bar" style={ratio} />
                  <span className="bars__share">
                    {Math.round((total_cents / data.expenses_cents) * 100)}%
                  </span>
                </span>
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

interface MonthlyChartProps {
  data: Dashboard
  onSelectMonth: (month: string) => void
}

/** Spending vs income per month on one shared axis. Each month is a button that selects it. */
function MonthlyChart({ data, onSelectMonth }: MonthlyChartProps) {
  const [hovered, setHovered] = useState<string | null>(null)
  const peak = Math.max(1, ...data.monthly.flatMap((m) => [m.expenses_cents, m.income_cents]))
  const height = (cents: number) => `${(cents / peak) * 100}%`
  const shown =
    data.monthly.find((m) => m.month === (hovered ?? data.month)) ??
    data.monthly[data.monthly.length - 1]

  return (
    <figure className="months">
      <ul className="legend" aria-hidden="true">
        <li>
          <span className="swatch swatch--out" /> Gastos
        </li>
        <li>
          <span className="swatch swatch--in" /> Entradas
        </li>
      </ul>
      <div className="months__plot" onMouseLeave={() => setHovered(null)}>
        {data.monthly.map((item) => (
          <button
            key={item.month}
            type="button"
            className="months__column"
            aria-pressed={item.month === data.month}
            aria-label={`${formatMonth(item.month)}: gastos ${formatMoney(item.expenses_cents)}, entradas ${formatMoney(item.income_cents)}`}
            onClick={() => onSelectMonth(item.month)}
            onMouseEnter={() => setHovered(item.month)}
            onFocus={() => setHovered(item.month)}
            onBlur={() => setHovered(null)}
          >
            <span className="months__bars" aria-hidden="true">
              <span
                className="months__bar months__bar--out"
                style={{ height: height(item.expenses_cents) }}
              />
              <span
                className="months__bar months__bar--in"
                style={{ height: height(item.income_cents) }}
              />
            </span>
            <span className="months__label" aria-hidden="true">
              {formatShortMonth(item.month)}
            </span>
          </button>
        ))}
      </div>
      {/* The readout plays the tooltip's role without ever overflowing a small screen. */}
      <figcaption className="months__readout" aria-hidden="true">
        <strong>{formatMonth(shown.month)}</strong>
        <span>
          <span className="swatch swatch--out" /> {formatMoney(shown.expenses_cents)}
        </span>
        <span>
          <span className="swatch swatch--in" /> {formatMoney(shown.income_cents)}
        </span>
      </figcaption>
    </figure>
  )
}
