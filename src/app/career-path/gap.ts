import type { CareerCost } from '../components/paths/types'

export type Position = 'high_school' | 'in_college' | 'has_degree' | 'working' | 'no_degree'

export const POSITIONS: { value: Position; label: string }[] = [
  { value: 'high_school', label: 'In high school' },
  { value: 'in_college', label: 'In college' },
  { value: 'has_degree', label: 'Have a degree' },
  { value: 'working', label: 'Working' },
  { value: 'no_degree', label: 'Not in school, no degree' },
]

/** Years of school each held credential represents. */
export const HELD_CREDENTIALS: { years: number; label: string }[] = [
  { years: 2, label: "Associate's" },
  { years: 4, label: "Bachelor's" },
  { years: 6, label: "Master's" },
]

const UNDERGRAD_YEARS = 4

export interface Gap {
  requiredYears: number
  creditedYears: number
  remainingYears: number
  remainingCost: number | null
  relevant: boolean
}

/**
 * How much education is left for the target career.
 * - A degree in a related field (linked to the target occupation) counts in full.
 * - An unrelated degree still counts toward graduate programs (any bachelor's
 *   qualifies), and unrelated college counts up to 2 years of general education.
 * Remaining cost scales the undergrad and graduate debt by the years left in each.
 */
export function computeGap({
  cost,
  completedYears,
  relevant,
}: {
  cost: CareerCost
  completedYears: number
  relevant: boolean
}): Gap {
  const required = cost.occupation.typical_years_of_school ?? 0
  let credited = completedYears
  if (!relevant) {
    credited = required > UNDERGRAD_YEARS ? Math.min(completedYears, UNDERGRAD_YEARS) : Math.min(completedYears, 2)
  }
  credited = Math.min(credited, required)
  const remaining = Math.max(0, required - credited)

  let remainingCost: number | null = null
  if (cost.medianDebt !== null && required > 0) {
    if (required <= UNDERGRAD_YEARS) {
      remainingCost = (cost.medianDebt * remaining) / required
    } else {
      const ugLeft = Math.max(0, UNDERGRAD_YEARS - credited)
      const gradYears = required - UNDERGRAD_YEARS
      const gradLeft = Math.max(0, required - Math.max(credited, UNDERGRAD_YEARS))
      remainingCost = (cost.undergradDebt * ugLeft) / UNDERGRAD_YEARS + (cost.medianDebt * gradLeft) / gradYears
    }
  } else if (required === 0) {
    remainingCost = 0
  }

  return {
    requiredYears: required,
    creditedYears: credited,
    remainingYears: remaining,
    remainingCost: remainingCost === null ? null : Math.round(remainingCost),
    relevant,
  }
}
