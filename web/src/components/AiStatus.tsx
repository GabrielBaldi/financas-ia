import { useMeta } from '../api/hooks'

export function AiStatus() {
  const { data } = useMeta()
  if (!data) return null
  return data.ai_enabled ? (
    <p className="ai-status ai-status--on" title={`Modelo: ${data.ai_model}`}>
      IA ligada
    </p>
  ) : (
    <p
      className="ai-status"
      title="Sem ANTHROPIC_API_KEY: o que as regras não reconhecem vai para A revisar"
    >
      IA desligada · só regras
    </p>
  )
}
