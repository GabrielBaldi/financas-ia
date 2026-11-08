import { useState, type FormEvent } from 'react'
import { useCreateRule } from '../api/hooks'
import type { Category } from '../api/types'
import { useCategoryLabel } from '../lib/labels'

export interface PendingRule {
  transactionId: number
  category: Category
  pattern: string
  count: number
}

interface Props {
  pending: PendingRule
  onDone: () => void
}

/** After a manual correction: offer to turn it into a rule ("aplicar a transações parecidas"). */
export function RuleSuggestion({ pending, onDone }: Props) {
  const [pattern, setPattern] = useState(pending.pattern)
  const createRule = useCreateRule()
  const label = useCategoryLabel()

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    createRule.mutate({ pattern, category: pending.category })
  }

  if (createRule.isSuccess) {
    const { applied, rule } = createRule.data
    return (
      <div className="notice">
        <p>
          Regra criada: descrições com “{rule.pattern}” viram{' '}
          <strong>{label(rule.category)}</strong>.{' '}
          {applied === 1 ? '1 transação atualizada.' : `${applied} transações atualizadas.`}
        </p>
        <button type="button" className="button button--quiet" onClick={onDone}>
          Fechar
        </button>
      </div>
    )
  }

  return (
    <form className="notice" onSubmit={submit} aria-labelledby="rule-title">
      <h2 id="rule-title">Aplicar “{label(pending.category)}” a transações parecidas?</h2>
      <p>
        {pending.count === 0
          ? 'Nenhuma outra transação parecida agora, mas a regra vale para os próximos extratos.'
          : `${pending.count} ${pending.count === 1 ? 'transação parecida' : 'transações parecidas'} com “${pending.pattern}”.`}
      </p>
      <label className="field">
        <span>Descrições que contêm</span>
        <input
          value={pattern}
          minLength={3}
          maxLength={120}
          required
          onChange={(event) => setPattern(event.target.value)}
        />
      </label>
      {createRule.isError && (
        <p className="error" role="alert">
          {createRule.error.message}
        </p>
      )}
      <div className="actions">
        <button type="submit" className="button" disabled={createRule.isPending}>
          {createRule.isPending ? 'Aplicando…' : 'Criar regra e aplicar'}
        </button>
        <button type="button" className="button button--quiet" onClick={onDone}>
          Agora não
        </button>
      </div>
    </form>
  )
}
