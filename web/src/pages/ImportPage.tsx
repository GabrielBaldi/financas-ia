import { useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { useImports, useImportStatement, useMeta } from '../api/hooks'
import type { ImportSummary } from '../api/types'
import { PipelineBar } from '../components/PipelineBar'
import { formatDateTime, formatUsd } from '../lib/format'
import genericCsvUrl from '../../../samples/extrato-generico.csv?url'
import ofxUrl from '../../../samples/extrato.ofx?url'
import nubankCardUrl from '../../../samples/nubank-cartao.csv?url'
import nubankAccountUrl from '../../../samples/nubank-conta.csv?url'

// Fictional statements from the repository, so reviewers can try an import right away.
const SAMPLES = [
  { url: nubankCardUrl, name: 'nubank-cartao.csv', label: 'Nubank, cartão (CSV)' },
  { url: nubankAccountUrl, name: 'nubank-conta.csv', label: 'Nubank, conta (CSV)' },
  {
    url: genericCsvUrl,
    name: 'extrato-generico.csv',
    label: 'CSV genérico (data;descrição;valor)',
  },
  { url: ofxUrl, name: 'extrato.ofx', label: 'OFX (SGML, Latin-1)' },
]

const FORMAT_LABELS: Record<string, string> = {
  ofx: 'OFX',
  nubank_cartao: 'Nubank cartão',
  nubank_conta: 'Nubank conta',
  csv_generico: 'CSV genérico',
}

function layerCounts(summary: ImportSummary) {
  return {
    user_rule: summary.by_user_rule,
    keyword: summary.by_keyword,
    ai: summary.by_ai,
    review: summary.to_review,
  }
}

export function ImportPage() {
  const history = useImports()
  const meta = useMeta()
  const importStatement = useImportStatement()
  const [file, setFile] = useState<File | null>(null)
  const accounts = [...new Set(history.data?.map((item) => item.account.name))]
  const [typedAccount, setTypedAccount] = useState<string | null>(null)
  const accountName = typedAccount ?? accounts[0] ?? ''

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (file) importStatement.mutate({ file, accountName }) // errors render from the mutation state
  }

  return (
    <>
      <header className="page__head">
        <h1>Importar extrato</h1>
        <p>
          Aceita OFX, o CSV exportado pelo Nubank (cartão ou conta) e CSV no formato{' '}
          <code>data;descrição;valor</code> com datas dd/mm/aaaa. O formato é detectado sozinho, e
          transações que já estão salvas são ignoradas.
        </p>
      </header>

      <div className="import-grid">
        <form className="card form" onSubmit={submit}>
          <label className="field">
            <span>Conta</span>
            <input
              list="accounts"
              value={accountName}
              placeholder="Ex.: Conta Nubank"
              maxLength={80}
              required
              onChange={(event) => setTypedAccount(event.target.value)}
            />
            <datalist id="accounts">
              {accounts.map((name) => (
                <option key={name} value={name} />
              ))}
            </datalist>
          </label>
          <label className="field">
            <span>Arquivo (.ofx ou .csv, até 2 MB)</span>
            <input
              type="file"
              accept=".ofx,.csv,text/csv"
              required
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
          </label>
          {meta.data && !meta.data.ai_enabled && (
            <p className="hint">
              A IA está desligada nesta instalação: o que as regras não reconhecerem vai para “A
              revisar”.
            </p>
          )}
          {importStatement.isError && (
            <p className="error" role="alert">
              {importStatement.error.message}
            </p>
          )}
          <button type="submit" className="button" disabled={importStatement.isPending || !file}>
            {importStatement.isPending ? 'Importando…' : 'Importar'}
          </button>
        </form>

        <div aria-live="polite">
          {importStatement.data ? (
            <ImportResult summary={importStatement.data} />
          ) : (
            <section className="card" aria-labelledby="samples-title">
              <h2 id="samples-title">Sem extrato à mão?</h2>
              <p className="muted">Baixe um exemplo com dados fictícios e importe aqui:</p>
              <ul className="samples">
                {SAMPLES.map(({ url, name, label }) => (
                  <li key={name}>
                    <a href={url} download={name}>
                      {name}
                    </a>{' '}
                    <span className="muted">· {label}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      </div>

      <section aria-labelledby="history-title">
        <h2 id="history-title">Histórico</h2>
        {history.data?.length === 0 && <p className="empty">Nenhum extrato importado ainda.</p>}
        {history.data && history.data.length > 0 && (
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Quando</th>
                  <th scope="col">Arquivo</th>
                  <th scope="col">Conta</th>
                  <th scope="col" className="amount">
                    Novas
                  </th>
                  <th scope="col" className="amount">
                    Duplicadas
                  </th>
                  <th scope="col" className="amount">
                    IA
                  </th>
                  <th scope="col" className="amount">
                    A revisar
                  </th>
                  <th scope="col" className="amount">
                    Custo da IA
                  </th>
                </tr>
              </thead>
              <tbody>
                {history.data.map((item) => (
                  <tr key={item.id}>
                    <td>{formatDateTime(item.created_at)}</td>
                    <td>
                      {item.filename}{' '}
                      <span className="muted">
                        ({FORMAT_LABELS[item.file_format] ?? item.file_format})
                      </span>
                    </td>
                    <td>{item.account.name}</td>
                    <td className="amount">{item.inserted}</td>
                    <td className="amount">{item.duplicates}</td>
                    <td className="amount">{item.by_ai}</td>
                    <td className="amount">{item.to_review}</td>
                    <td className="amount">{formatUsd(item.ai_cost_usd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  )
}

function ImportResult({ summary }: { summary: ImportSummary }) {
  return (
    <section className="card result" aria-labelledby="result-title">
      <h2 id="result-title">Extrato importado</h2>
      <p>
        {summary.total_rows} linhas lidas ({FORMAT_LABELS[summary.file_format]}):{' '}
        <strong>{summary.inserted} novas</strong>, {summary.duplicates} já existiam.
      </p>
      <PipelineBar counts={layerCounts(summary)} label="Quem categorizou as transações novas" />
      {summary.ai_input_tokens > 0 && (
        <p className="muted">
          IA: {summary.ai_input_tokens} tokens de entrada e {summary.ai_output_tokens} de saída,
          cerca de {formatUsd(summary.ai_cost_usd)}.
        </p>
      )}
      {summary.to_review > 0 && (
        <Link className="button" to="/revisao?revisar=1">
          Revisar {summary.to_review} {summary.to_review === 1 ? 'transação' : 'transações'}
        </Link>
      )}
    </section>
  )
}
