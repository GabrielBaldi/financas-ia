import type { Source } from '../api/types'
import { formatPercent } from '../lib/format'
import { SOURCE_LABELS } from '../lib/labels'

interface Props {
  source: Source
  confidence?: number | null
}

/** Which layer decided the category, shown like a rubber stamp on the ledger line. */
export function SourceStamp({ source, confidence }: Props) {
  const showConfidence = source === 'ai' && confidence != null
  return (
    <span className={`stamp stamp--${source}`}>
      {SOURCE_LABELS[source]}
      {showConfidence && ` · ${formatPercent(confidence)}`}
    </span>
  )
}
