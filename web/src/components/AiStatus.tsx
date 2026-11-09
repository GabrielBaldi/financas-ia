import { useMeta } from '../api/hooks'
import { aiStatusLabel } from '../lib/ai'

export function AiStatus() {
  const { data } = useMeta()
  if (!data) return null
  return data.ai_enabled ? (
    <p
      className="ai-status ai-status--on"
      title="Só a descrição e o valor do que as regras não reconhecem vão para a IA"
    >
      {aiStatusLabel(data)}
    </p>
  ) : (
    <p
      className="ai-status"
      title="Sem ANTHROPIC_API_KEY ou NVIDIA_API_KEY: o que as regras não reconhecem vai para A revisar"
    >
      {aiStatusLabel(data)}
    </p>
  )
}
