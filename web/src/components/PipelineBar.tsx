import type { Source } from '../api/types'
import { SOURCE_LABELS } from '../lib/labels'

export type SourceCounts = Partial<Record<Source, number>>

const ORDER: Source[] = ['user_rule', 'keyword', 'ai', 'manual', 'review']

/** A stacked bar showing how many transactions each layer of the pipeline decided. */
export function PipelineBar({ counts, label }: { counts: SourceCounts; label: string }) {
  const entries = ORDER.map((source) => [source, counts[source] ?? 0] as const).filter(
    ([, count]) => count > 0,
  )
  const total = entries.reduce((sum, [, count]) => sum + count, 0)
  if (total === 0) return null

  return (
    <figure className="pipeline">
      <figcaption className="visually-hidden">{label}</figcaption>
      <div className="pipeline__bar" aria-hidden="true">
        {entries.map(([source, count]) => (
          <span
            key={source}
            className={`pipeline__segment pipeline__segment--${source}`}
            style={{ flexGrow: count }}
          />
        ))}
      </div>
      <ul className="pipeline__legend">
        {entries.map(([source, count]) => (
          <li key={source}>
            <span className={`swatch swatch--${source}`} aria-hidden="true" />
            {SOURCE_LABELS[source]} <strong>{count}</strong>
          </li>
        ))}
      </ul>
    </figure>
  )
}
