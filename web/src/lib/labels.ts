import { useMeta } from '../api/hooks'
import type { Category, Source } from '../api/types'

export const REVIEW_LABEL = 'A revisar'

export const SOURCE_LABELS: Record<Source, string> = {
  user_rule: 'Sua regra',
  keyword: 'Regra padrão',
  ai: 'IA',
  manual: 'Você',
  review: REVIEW_LABEL,
}

/** Category names come from the API (/meta), so the back-end stays the single source. */
export function useCategoryLabel(): (category: Category | null) => string {
  const { data } = useMeta()
  return (category) => {
    if (category === null) return REVIEW_LABEL
    return data?.categories.find((item) => item.slug === category)?.label ?? category
  }
}
