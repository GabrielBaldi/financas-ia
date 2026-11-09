import { useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { fetchSimilar, useSetCategory, useTransactions } from '../api/hooks'
import type { Category, Transaction } from '../api/types'
import { PipelineBar, type SourceCounts } from '../components/PipelineBar'
import { CategorySelect, MonthSelect } from '../components/Selects'
import { SourceStamp } from '../components/SourceStamp'
import { formatDayMonth, formatMonth, formatPercent, formatSignedMoney } from '../lib/format'
import { REVIEW_LABEL, useCategoryLabel } from '../lib/labels'
import { useSelectedMonth } from '../lib/useSelectedMonth'
import { RuleSuggestion, type PendingRule } from './RuleSuggestion'

function countBySource(items: Transaction[]): SourceCounts {
  const counts: SourceCounts = {}
  for (const { categorized_by } of items) {
    counts[categorized_by] = (counts[categorized_by] ?? 0) + 1
  }
  return counts
}

export function ReviewPage() {
  const { month, setMonth, months } = useSelectedMonth()
  const [params, setParams] = useSearchParams()
  const category = (params.get('categoria') ?? '') as Category | ''
  const toReview = params.get('revisar') === '1'
  const transactions = useTransactions({ month, category, toReview })
  const setCategory = useSetCategory()
  const [pendingRule, setPendingRule] = useState<PendingRule | null>(null)
  const [changeError, setChangeError] = useState<string | null>(null)
  const label = useCategoryLabel()

  function setFilter(key: string, value: string) {
    setParams(
      (current) => {
        if (value) current.set(key, value)
        else current.delete(key)
        return current
      },
      { replace: true },
    )
  }

  async function changeCategory(transaction: Transaction, next: Category) {
    setChangeError(null)
    try {
      await setCategory.mutateAsync({ id: transaction.id, category: next })
      const similar = await fetchSimilar(transaction.id)
      setPendingRule({ transactionId: transaction.id, category: next, ...similar })
    } catch (failure) {
      setChangeError(failure instanceof Error ? failure.message : 'Não foi possível salvar.')
    }
  }

  const items = transactions.data?.items ?? []
  const counts = countBySource(items)

  return (
    <>
      <header className="page__head">
        <h1>Revisão</h1>
        <p>
          Confira quem decidiu cada categoria. Ao corrigir uma, você pode transformar a correção em
          regra para os próximos extratos.
        </p>
      </header>

      <fieldset className="toolbar">
        <legend className="visually-hidden">Filtros</legend>
        <div className="field field--inline">
          <label htmlFor="filter-month">Mês</label>
          <MonthSelect id="filter-month" months={months} value={month} onChange={setMonth} />
        </div>
        <div className="field field--inline">
          <label htmlFor="filter-category">Categoria</label>
          <CategorySelect
            id="filter-category"
            value={category}
            emptyLabel="Todas"
            onChange={(value) => setFilter('categoria', value)}
          />
        </div>
        <label className="check">
          <input
            type="checkbox"
            checked={toReview}
            onChange={(event) => setFilter('revisar', event.target.checked ? '1' : '')}
          />
          Só “{REVIEW_LABEL}”
        </label>
      </fieldset>

      {/* Announced politely instead of moving focus away from the row being edited. */}
      <div aria-live="polite">
        {pendingRule && (
          <RuleSuggestion
            key={`${pendingRule.transactionId}-${pendingRule.category}`}
            pending={pendingRule}
            onDone={() => setPendingRule(null)}
          />
        )}
      </div>
      {changeError && (
        <p className="error" role="alert">
          {changeError}
        </p>
      )}

      <section aria-labelledby="ledger-title">
        <div className="ledger__summary">
          <h2 id="ledger-title">
            {formatMonth(month)}
            <span className="muted">
              {' '}
              · {transactions.data?.total ?? 0} transações
              {(counts.review ?? 0) > 0 && ` · ${counts.review} a revisar`}
            </span>
          </h2>
          <PipelineBar counts={counts} label="Quem categorizou as transações listadas" />
        </div>

        {transactions.isPending && <p role="status">Carregando transações…</p>}
        {transactions.isError && (
          <p className="error" role="alert">
            {transactions.error.message}
          </p>
        )}
        {transactions.isSuccess && items.length === 0 && (
          <p className="empty">
            Nenhuma transação aqui. <Link to="/importar">Importe um extrato</Link> ou mude os
            filtros.
          </p>
        )}

        {items.length > 0 && (
          <table className="ledger">
            <thead>
              <tr>
                <th scope="col">Data</th>
                <th scope="col">Descrição</th>
                <th scope="col">Categoria</th>
                <th scope="col">Decidido por</th>
                <th scope="col" className="amount">
                  Valor
                </th>
              </tr>
            </thead>
            <tbody>
              {items.map((transaction) => (
                <LedgerRow
                  key={transaction.id}
                  transaction={transaction}
                  suggestionLabel={
                    transaction.suggested_category && label(transaction.suggested_category)
                  }
                  onChange={(next) => changeCategory(transaction, next)}
                />
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  )
}

interface RowProps {
  transaction: Transaction
  suggestionLabel: string | null
  onChange: (category: Category) => void
}

function LedgerRow({ transaction, suggestionLabel, onChange }: RowProps) {
  const { date, description, amount_cents, category, categorized_by, confidence, origin, note } =
    transaction
  return (
    <tr className={category === null ? 'ledger__row ledger__row--review' : 'ledger__row'}>
      <td className="ledger__date">{formatDayMonth(date)}</td>
      <td className="ledger__description">
        {description}
        {origin === 'telegram' && (
          <span className="tag">
            Telegram<span className="visually-hidden">, ainda não conferido com o extrato</span>
          </span>
        )}
        {note && (
          <small className="ledger__note">
            <span className="visually-hidden">Sua anotação: </span>
            {note}
          </small>
        )}
      </td>
      <td className="ledger__category">
        <CategorySelect
          aria-label={`Categoria de ${description}`}
          value={category ?? ''}
          emptyLabel={category === null ? `${REVIEW_LABEL}…` : undefined}
          emptyDisabled
          onChange={(next) => next && onChange(next)}
        />
        {suggestionLabel && confidence != null && (
          <small className="hint">
            IA sugeriu {suggestionLabel} ({formatPercent(confidence)})
          </small>
        )}
      </td>
      <td className="ledger__source">
        <SourceStamp source={categorized_by} confidence={confidence} />
      </td>
      <td className={amount_cents > 0 ? 'amount amount--in' : 'amount'}>
        {formatSignedMoney(amount_cents)}
      </td>
    </tr>
  )
}
