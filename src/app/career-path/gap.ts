import type { CareerCost } from '../components/paths/types'

export type Position = 'high_school' | 'in_college' | 'working' | 'looking_for_work'

export const POSITIONS: { value: Position; label: string }[] = [
  { value: 'high_school', label: 'In high school' },
  { value: 'in_college', label: 'In college' },
  { value: 'working', label: 'Working' },
  { value: 'looking_for_work', label: 'Looking for work' },
]

export type EducationLevel =
  | 'no_hs'
  | 'hs'
  | 'some_college'
  | 'certificate'
  | 'associate'
  | 'bachelor'
  | 'master'
  | 'doctoral'

/**
 * Highest education for people who are working or looking for work.
 * `years` is school credited toward a career; null means ask for years completed.
 * `hasField` means ask what the education was in.
 * Certificates count 0 years, matching how O*NET-based career years treat them.
 */
export const EDUCATION_LEVELS: { value: EducationLevel; label: string; years: number | null; hasField: boolean }[] = [
  { value: 'no_hs', label: 'No high school diploma', years: 0, hasField: false },
  { value: 'hs', label: 'High school diploma or GED', years: 0, hasField: false },
  { value: 'some_college', label: 'Some college, no degree', years: null, hasField: true },
  { value: 'certificate', label: 'Certificate', years: 0, hasField: true },
  { value: 'associate', label: "Associate's", years: 2, hasField: true },
  { value: 'bachelor', label: "Bachelor's", years: 4, hasField: true },
  { value: 'master', label: "Master's", years: 6, hasField: true },
  { value: 'doctoral', label: 'Doctoral or professional', years: 8, hasField: true },
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
