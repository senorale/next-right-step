// Education cost for an occupation: occupation -> CipOccupation -> CipCode ->
// ProgramDebt. Debt is the average of median_debt across every degree field
// linked to the occupation, weighted by ProgramDebt.sample_size, at the
// credential level that matches the occupation's typical years of school.
import { prisma } from './prisma'

export interface CareerCost {
  occupation: {
    id: string
    name: string
    occupation_code: string
    annual_salary: number
    typical_years_of_school: number | null
  }
  /** Credential levels used for the debt lookup, empty when no school is required. */
  credentialLevels: number[]
  credentialLabel: string | null
  /** Weighted median debt for the target credential, null when school is required but no debt data exists. */
  medianDebt: number | null
  debtSampleSize: number
  /** True when no linked field had debt data and medianDebt comes from the fields' 2-digit CIP families. */
  debtEstimated: boolean
  /** Graduate credentials also require a bachelor's: national weighted bachelor's debt, else 0. */
  undergradDebt: number
  /** medianDebt + undergradDebt, null when medianDebt is null. */
  totalDebt: number | null
  degrees: { code: string; title: string }[]
}

// ProgramDebt / Scorecard CREDLEV codes by typical years of school.
function credentialLevelsForYears(years: number): number[] {
  if (years <= 0) return []
  if (years <= 1) return [1]
  if (years <= 2) return [2]
  if (years <= 4) return [3]
  if (years <= 6) return [5]
  return [6, 7]
}

const CREDENTIAL_LABELS: Record<number, string> = {
  1: 'Certificate',
  2: "Associate's degree",
  3: "Bachelor's degree",
  5: "Master's degree",
  6: 'Doctoral or professional degree',
  7: 'Doctoral or professional degree',
}

let bachelorsDebtCache: number | null = null

/** Weighted median bachelor's debt across all degree fields. */
export async function nationalBachelorsDebt(): Promise<number> {
  if (bachelorsDebtCache !== null) return bachelorsDebtCache
  const rows = await prisma.programDebt.findMany({
    where: { school_type: 'all', credential_level: 3 },
    select: { median_debt: true, sample_size: true },
  })
  const n = rows.reduce((s, r) => s + r.sample_size, 0)
  bachelorsDebtCache = n > 0 ? Math.round(rows.reduce((s, r) => s + r.median_debt * r.sample_size, 0) / n) : 0
  return bachelorsDebtCache
}

/**
 * Fallback when none of an occupation's degree fields report debt: weighted
 * median debt across every field in the same 2-digit CIP families (e.g. 45xx
 * Social Sciences for Sociology 4511) at the target credential levels.
 */
async function familyDebt(cipCodes: string[], levels: number[]): Promise<{ debt: number; sampleSize: number } | null> {
  const families = [...new Set(cipCodes.map((c) => c.slice(0, 2)))]
  if (families.length === 0) return null
  const rows = await prisma.programDebt.findMany({
    where: {
      school_type: 'all',
      credential_level: { in: levels },
      sample_size: { gt: 0 },
      cip: { OR: families.map((f) => ({ code: { startsWith: f } })) },
    },
    select: { median_debt: true, sample_size: true },
  })
  const n = rows.reduce((s, r) => s + r.sample_size, 0)
  if (n === 0) return null
  return { debt: Math.round(rows.reduce((s, r) => s + r.median_debt * r.sample_size, 0) / n), sampleSize: n }
}

export async function getCareerCost(where: { id: string } | { occupation_code: string }): Promise<CareerCost | null> {
  const occupation = await prisma.occupationSubCategory.findFirst({
    where,
    select: {
      id: true,
      name: true,
      occupation_code: true,
      annual_salary: true,
      typical_years_of_school: true,
      cip_mappings: {
        select: {
          cip: {
            select: {
              code: true,
              title: true,
              debt: {
                where: { school_type: 'all' },
                select: { credential_level: true, median_debt: true, sample_size: true },
              },
            },
          },
        },
      },
    },
  })
  if (!occupation) return null

  const years = occupation.typical_years_of_school ?? 0
  const levels = credentialLevelsForYears(years)

  let weightedSum = 0
  let sampleSize = 0
  for (const { cip } of occupation.cip_mappings) {
    for (const d of cip.debt) {
      if (!levels.includes(d.credential_level) || d.sample_size <= 0) continue
      weightedSum += d.median_debt * d.sample_size
      sampleSize += d.sample_size
    }
  }

  let medianDebt = levels.length === 0 ? 0 : sampleSize > 0 ? Math.round(weightedSum / sampleSize) : null
  let debtEstimated = false
  if (medianDebt === null) {
    const family = await familyDebt(occupation.cip_mappings.map(({ cip }) => cip.code), levels)
    if (family) {
      medianDebt = family.debt
      sampleSize = family.sampleSize
      debtEstimated = true
    }
  }
  const isGraduate = levels.some((l) => l >= 5)
  const undergradDebt = isGraduate ? await nationalBachelorsDebt() : 0

  const { cip_mappings, ...rest } = occupation
  return {
    occupation: rest,
    credentialLevels: levels,
    credentialLabel: levels.length > 0 ? CREDENTIAL_LABELS[levels[0]] : null,
    medianDebt,
    debtSampleSize: sampleSize,
    debtEstimated,
    undergradDebt,
    totalDebt: medianDebt === null ? null : medianDebt + undergradDebt,
    degrees: cip_mappings.map(({ cip }) => ({ code: cip.code, title: cip.title.replace(/\.$/, '') })),
  }
}
