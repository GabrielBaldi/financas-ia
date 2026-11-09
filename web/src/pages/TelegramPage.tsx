import { useEffect, useState } from 'react'
import {
  useAccounts,
  useCreatePairingCode,
  useSetDefaultAccount,
  useTelegramStatus,
  useUnlinkTelegram,
} from '../api/hooks'
import type { PairingCode, TelegramStatus } from '../api/types'
import { formatDateTime } from '../lib/format'
import { connectCommand, formatCountdown, secondsLeft } from '../lib/telegram'

const MANUAL_ACCOUNT = 'Lançamentos manuais'

const EXAMPLES = ['32,90 almoço', 'uber 23 ontem', 'mercado 150 #nubank', '+50 pix recebido']

/** The current time, ticking every second while `active`. */
function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!active) return
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [active])
  return now
}

interface Pairing extends PairingCode {
  /** linked_at when the code was created: a different value means the chat just connected. */
  linkedAtBefore: string | null
}

export function TelegramPage() {
  const [pairing, setPairing] = useState<Pairing | null>(null)
  const now = useNow(pairing !== null)
  const codeAlive = pairing !== null && secondsLeft(pairing.expires_at, now) > 0
  const status = useTelegramStatus({ watch: codeAlive })
  const createCode = useCreatePairingCode()

  const justLinked =
    pairing !== null &&
    status.data?.linked === true &&
    status.data.linked_at !== pairing.linkedAtBefore

  function generate() {
    const linkedAtBefore = status.data?.linked_at ?? null
    createCode.mutate(undefined, { onSuccess: (code) => setPairing({ ...code, linkedAtBefore }) })
  }

  return (
    <>
      <header className="page__head">
        <h1>Telegram</h1>
        <p>
          Anote um gasto pelo celular na hora em que ele acontece. Quando o extrato chegar, o app
          confere: o lançamento vira uma nota na linha do banco e nada é contado duas vezes.
        </p>
      </header>

      {status.isPending && <p role="status">Carregando…</p>}
      {status.isError && (
        <p className="error" role="alert">
          {status.error.message}
        </p>
      )}

      {status.data && (
        <div className="telegram-grid">
          <section className="card telegram-card" aria-labelledby="link-title">
            <h2 id="link-title">Conexão</h2>
            <LinkStatus status={status.data} />
            <div aria-live="polite">
              {justLinked && <p className="notice">Pronto: o chat foi conectado.</p>}
              {pairing && !justLinked && (
                <PairingSteps pairing={pairing} remaining={secondsLeft(pairing.expires_at, now)} />
              )}
            </div>
            {createCode.isError && (
              <p className="error" role="alert">
                {createCode.error.message}
              </p>
            )}
            {!codeAlive || justLinked ? (
              <div className="actions">
                <button
                  type="button"
                  className="button"
                  disabled={createCode.isPending}
                  onClick={generate}
                >
                  {status.data.linked ? 'Gerar código para outro chat' : 'Gerar código'}
                </button>
              </div>
            ) : null}
          </section>

          <DefaultAccount status={status.data} />
        </div>
      )}

      <section className="card telegram-card" aria-labelledby="howto-title">
        <h2 id="howto-title">Como mandar</h2>
        <p>Um gasto por mensagem, com o valor e uma descrição, em qualquer ordem:</p>
        <ul className="examples">
          {EXAMPLES.map((example) => (
            <li key={example}>
              <code>{example}</code>
            </li>
          ))}
        </ul>
        <p className="hint">
          Datas: <code>hoje</code>, <code>ontem</code>, <code>anteontem</code> ou <code>05/11</code>
          . <code>#nubank</code> escolhe a conta pelo começo do nome ou de uma palavra dele.
          Comandos: <code>/desfazer</code>, <code>/ultimos</code>, <code>/conta</code>,{' '}
          <code>/ajuda</code>.
        </p>
        <p className="hint">
          Privacidade: as mensagens passam pelos servidores do Telegram. O bot só responde ao chat
          conectado, e o seu computador só faz requisições de saída: nenhuma porta fica aberta.
        </p>
      </section>
    </>
  )
}

function LinkStatus({ status }: { status: TelegramStatus }) {
  const unlink = useUnlinkTelegram()

  function confirmUnlink() {
    if (window.confirm('Desconectar o Telegram? Os lançamentos já feitos continuam aqui.')) {
      unlink.mutate()
    }
  }

  if (!status.linked) {
    return (
      <p className="link-status">
        <span className="link-status__dot" aria-hidden="true" />
        Nenhum chat conectado.
      </p>
    )
  }
  return (
    <>
      <p className="link-status link-status--on">
        <span className="link-status__dot" aria-hidden="true" />
        Conectado
        {status.linked_at && <> desde {formatDateTime(status.linked_at)}</>}.
      </p>
      {unlink.isError && (
        <p className="error" role="alert">
          {unlink.error.message}
        </p>
      )}
      <div className="actions">
        <button
          type="button"
          className="button button--quiet"
          disabled={unlink.isPending}
          onClick={confirmUnlink}
        >
          Desconectar
        </button>
      </div>
    </>
  )
}

function PairingSteps({ pairing, remaining }: { pairing: Pairing; remaining: number }) {
  const [copied, setCopied] = useState(false)
  const command = connectCommand(pairing.code)

  async function copy() {
    try {
      await navigator.clipboard.writeText(command)
      setCopied(true)
    } catch {
      setCopied(false) // no clipboard permission: the command is on screen to type
    }
  }

  if (remaining === 0) {
    return <p className="hint">O código expirou. Gere outro quando for conectar.</p>
  }
  return (
    <div className="pairing">
      <p className="pairing__code" aria-label={`Código ${pairing.code.split('').join(' ')}`}>
        {pairing.code}
      </p>
      <p className="hint">
        Vale uma vez, por mais <span role="timer">{formatCountdown(remaining)}</span>.
      </p>
      <ol className="steps steps--compact">
        <li>
          <span>
            No Telegram, abra o seu bot (o que você criou no <strong>@BotFather</strong>).
          </span>
        </li>
        <li>
          <span>
            Envie <code>{command}</code>{' '}
            <button type="button" className="link-button" onClick={copy}>
              {copied ? 'Copiado' : 'Copiar'}
            </button>
          </span>
        </li>
        <li>
          <span>Esta página mostra “Conectado” sozinha.</span>
        </li>
      </ol>
      <p className="hint">
        O bot precisa estar rodando no seu computador:{' '}
        <code>uv run python -m financas.telegram_bot</code>.
      </p>
    </div>
  )
}

function DefaultAccount({ status }: { status: TelegramStatus }) {
  const accounts = useAccounts()
  const setDefault = useSetDefaultAccount()
  const selected = status.default_account?.id ?? ''

  return (
    <section className="card telegram-card" aria-labelledby="account-title">
      <h2 id="account-title">Conta padrão</h2>
      <div className="field">
        <label htmlFor="telegram-account">Lançamentos sem #conta vão para</label>
        <select
          id="telegram-account"
          aria-describedby="telegram-account-hint"
          value={selected}
          disabled={setDefault.isPending || !accounts.data}
          onChange={(event) =>
            setDefault.mutate(event.target.value ? Number(event.target.value) : null)
          }
        >
          <option value="">{MANUAL_ACCOUNT}</option>
          {accounts.data
            ?.filter((account) => account.name !== MANUAL_ACCOUNT)
            .map((account) => (
              <option key={account.id} value={account.id}>
                {account.name}
              </option>
            ))}
        </select>
      </div>
      <p id="telegram-account-hint" className="hint">
        Escolha a conta com o mesmo nome que você usa ao importar o extrato desse cartão. É assim
        que, na importação, o app reconhece os gastos que você já anotou (mesmo valor, até 3 dias de
        diferença).
      </p>
      <div aria-live="polite">
        {setDefault.isSuccess && <p className="hint">Conta padrão salva.</p>}
        {setDefault.isError && (
          <p className="error" role="alert">
            {setDefault.error.message}
          </p>
        )}
      </div>
    </section>
  )
}
