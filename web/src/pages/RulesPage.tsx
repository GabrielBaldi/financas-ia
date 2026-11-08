import { useState, type FormEvent } from 'react'
import { useCreateRule, useDeleteRule, useRules } from '../api/hooks'
import type { Category, Rule } from '../api/types'
import { CategorySelect } from '../components/Selects'
import { formatDateTime } from '../lib/format'
import { useCategoryLabel } from '../lib/labels'

export function RulesPage() {
  const rules = useRules()
  const createRule = useCreateRule()
  const deleteRule = useDeleteRule()
  const label = useCategoryLabel()
  const [pattern, setPattern] = useState('')
  const [category, setCategory] = useState<Category | ''>('')

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!category) return
    createRule.mutate({ pattern, category }, { onSuccess: () => setPattern('') })
  }

  function remove(rule: Rule) {
    if (
      window.confirm(`Excluir a regra “${rule.pattern}”? As transações mantêm a categoria atual.`)
    ) {
      deleteRule.mutate(rule.id)
    }
  }

  return (
    <>
      <header className="page__head">
        <h1>Regras</h1>
        <p>
          Quando a descrição contém o padrão, a transação recebe a categoria. Suas regras valem
          antes das regras padrão e da IA, e, se duas servirem, vence a mais específica.
        </p>
      </header>

      <form className="card form form--row" onSubmit={submit}>
        <label className="field">
          <span>Descrições que contêm</span>
          <input
            value={pattern}
            minLength={3}
            maxLength={120}
            required
            placeholder="Ex.: padaria pao quente"
            onChange={(event) => setPattern(event.target.value)}
          />
        </label>
        <div className="field">
          <label htmlFor="rule-category">Categoria</label>
          <CategorySelect
            id="rule-category"
            value={category}
            emptyLabel="Escolha…"
            emptyDisabled
            required
            onChange={setCategory}
          />
        </div>
        <button type="submit" className="button" disabled={createRule.isPending}>
          Criar regra
        </button>
      </form>
      <div aria-live="polite">
        {createRule.isSuccess && (
          <p className="notice">
            Regra salva. {createRule.data.applied}{' '}
            {createRule.data.applied === 1 ? 'transação atualizada' : 'transações atualizadas'}.
          </p>
        )}
        {(createRule.isError || deleteRule.isError) && (
          <p className="error" role="alert">
            {(createRule.error ?? deleteRule.error)?.message}
          </p>
        )}
      </div>

      {rules.data?.length === 0 && (
        <p className="empty">
          Nenhuma regra ainda. Corrija uma categoria na Revisão e escolha “Criar regra e aplicar”.
        </p>
      )}
      {rules.data && rules.data.length > 0 && (
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Padrão</th>
                <th scope="col">Categoria</th>
                <th scope="col">Criada em</th>
                <th scope="col">
                  <span className="visually-hidden">Ações</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {rules.data.map((rule) => (
                <tr key={rule.id}>
                  <td>
                    <code>{rule.pattern}</code>
                  </td>
                  <td>{label(rule.category)}</td>
                  <td>{formatDateTime(rule.created_at)}</td>
                  <td className="amount">
                    <button
                      type="button"
                      className="button button--quiet"
                      aria-label={`Excluir a regra ${rule.pattern}`}
                      onClick={() => remove(rule)}
                    >
                      Excluir
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
