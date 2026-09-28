// College Scorecard API client. Shared by the seed scripts and the runtime
// fallback in /api/schools, so both write School / SchoolProgram rows the same
// way. Uses relative imports only so ts-node scripts can load it.
import type { Prisma, PrismaClient } from '@prisma/client'

const BASE_URL = 'https://api.data.gov/ed/collegescorecard/v1/schools'

// Scorecard field-of-study CREDLEV codes
export const CREDENTIAL_LABELS: Record<number, string> = {
  1: 'Undergraduate certificate',
  2: "Associate's",
  3: "Bachelor's",
  4: 'Post-baccalaureate certificate',
  5: "Master's",
  6: 'Doctoral',
  7: 'First professional degree',
  8: 'Graduate/professional certificate',
}

const OWNERSHIP_LABELS: Record<number, string> = {
  1: 'Public',
  2: 'Private nonprofit',
  3: 'Private for-profit',
}

const INCOME_BRACKETS = ['0-30000', '30001-48000', '48001-75000', '75001-110000', '110001-plus'] as const

const SCHOOL_FIELDS = [
  'id',
  'school.name',
  'school.city',
  'school.state',
  'school.school_url',
  'school.ownership',
  'latest.student.size',
  'latest.cost.tuition.in_state',
  'latest.cost.tuition.out_of_state',
  'latest.cost.avg_net_price.overall',
  ...INCOME_BRACKETS.map((b) => `latest.cost.net_price.consumer.by_income_level.${b}`),
  'latest.completion.rate_suppressed.overall',
  'latest.aid.median_debt_suppressed.overall',
  'latest.earnings.6_yrs_after_entry.median',
  'latest.earnings.10_yrs_after_entry.median',
  'latest.admissions.admission_rate.overall',
  'latest.student.retention_rate.four_year.full_time',
  // No overall 3-year repayment rate exists (3_yr_repayment.overall is a
  // borrower count), so it is derived from the completer/noncompleter splits.
  'latest.repayment.3_yr_repayment.completers',
  'latest.repayment.3_yr_repayment.completers_rate',
  'latest.repayment.3_yr_repayment.noncompleters',
  'latest.repayment.3_yr_repayment.noncompleters_rate',
].join(',')

const PROGRAM_PREFIX = 'latest.programs.cip_4_digit'
const PROGRAM_FIELDS = [
  'id',
  `${PROGRAM_PREFIX}.code`,
  `${PROGRAM_PREFIX}.title`,
  `${PROGRAM_PREFIX}.credential.level`,
  `${PROGRAM_PREFIX}.earnings.1_yr.overall_median_earnings`,
  `${PROGRAM_PREFIX}.earnings.4_yr.overall_median_earnings`,
  `${PROGRAM_PREFIX}.debt.staff_grad_plus.all.eval_inst.median`,
].join(',')

type ScorecardRow = Record<string, unknown>

export type SchoolRow = Omit<Prisma.SchoolCreateManyInput, 'fetched_at' | 'created_at' | 'updated_at'>
export type SchoolProgramRow = Omit<Prisma.SchoolProgramCreateManyInput, 'id' | 'fetched_at' | 'created_at' | 'updated_at'>

export interface ScorecardPage {
  total: number
  results: ScorecardRow[]
}

export interface SchoolQuery {
  name?: string
  state?: string
  /** school.degrees_awarded.predominant, e.g. 3 = bachelor's */
  predominantDegree?: number
  id?: number
}

function apiKey(): string {
  const key = process.env.COLLEGE_SCORECARD_API_KEY
  if (!key) throw new Error('COLLEGE_SCORECARD_API_KEY is not set')
  return key
}

function num(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null
}

function int(v: unknown): number | null {
  const n = num(v)
  return n === null ? null : Math.round(n)
}

function str(v: unknown): string | null {
  return typeof v === 'string' && v.length > 0 ? v : null
}

function obj(v: unknown): Record<string, unknown> {
  return v !== null && typeof v === 'object' ? (v as Record<string, unknown>) : {}
}

/** Walk a nested object by dotted path, e.g. get(p, 'earnings.1_yr.overall_median_earnings'). */
function get(root: Record<string, unknown>, path: string): unknown {
  return path.split('.').reduce<unknown>((cur, key) => obj(cur)[key], root)
}

async function fetchPage(
  fields: string,
  query: SchoolQuery,
  page: number,
  perPage: number
): Promise<ScorecardPage> {
  const params = new URLSearchParams({
    api_key: apiKey(),
    fields,
    page: String(page),
    per_page: String(perPage),
    'school.operating': '1',
  })
  if (query.id !== undefined) params.set('id', String(query.id))
  if (query.name) params.set('school.name', query.name)
  if (query.state) params.set('school.state', query.state.toUpperCase())
  if (query.predominantDegree !== undefined) {
    params.set('school.degrees_awarded.predominant', String(query.predominantDegree))
  }

  const resp = await fetch(`${BASE_URL}?${params}`, { cache: 'no-store' })
  if (!resp.ok) {
    throw new Error(`Scorecard API returned ${resp.status}`)
  }
  const body = obj(await resp.json())
  const results = Array.isArray(body.results) ? (body.results as ScorecardRow[]) : []
  const total = num(obj(body.metadata).total) ?? results.length
  return { total, results }
}

export function fetchSchoolsPage(query: SchoolQuery, page: number, perPage = 100): Promise<ScorecardPage> {
  return fetchPage(SCHOOL_FIELDS, query, page, perPage)
}

export function fetchProgramsPage(query: SchoolQuery, page: number, perPage = 20): Promise<ScorecardPage> {
  return fetchPage(PROGRAM_FIELDS, query, page, perPage)
}

function repaymentRate3yr(r: ScorecardRow): number | null {
  const completers = num(r['latest.repayment.3_yr_repayment.completers'])
  const completersRate = num(r['latest.repayment.3_yr_repayment.completers_rate'])
  const noncompleters = num(r['latest.repayment.3_yr_repayment.noncompleters'])
  const noncompletersRate = num(r['latest.repayment.3_yr_repayment.noncompleters_rate'])
  if (completers === null || completersRate === null || noncompleters === null || noncompletersRate === null) {
    return null
  }
  const borrowers = completers + noncompleters
  if (borrowers === 0) return null
  return (completers * completersRate + noncompleters * noncompletersRate) / borrowers
}

/** Returns null when the row lacks the fields School requires. */
export function mapSchool(r: ScorecardRow): SchoolRow | null {
  const schoolId = int(r.id)
  const name = str(r['school.name'])
  const city = str(r['school.city'])
  const state = str(r['school.state'])
  if (schoolId === null || !name || !city || !state) return null

  const byIncome: Record<string, number | null> = {}
  for (const b of INCOME_BRACKETS) {
    byIncome[b] = int(r[`latest.cost.net_price.consumer.by_income_level.${b}`])
  }

  return {
    school_id: schoolId,
    name,
    city,
    state,
    school_type: OWNERSHIP_LABELS[int(r['school.ownership']) ?? 0] ?? 'Unknown',
    url: str(r['school.school_url']),
    student_size: int(r['latest.student.size']),
    tuition_in_state: int(r['latest.cost.tuition.in_state']),
    tuition_out_of_state: int(r['latest.cost.tuition.out_of_state']),
    avg_net_price: int(r['latest.cost.avg_net_price.overall']),
    net_price_by_income: byIncome,
    graduation_rate: num(r['latest.completion.rate_suppressed.overall']),
    median_debt: int(r['latest.aid.median_debt_suppressed.overall']),
    earnings_6yr: int(r['latest.earnings.6_yrs_after_entry.median']),
    earnings_10yr: int(r['latest.earnings.10_yrs_after_entry.median']),
    admission_rate: num(r['latest.admissions.admission_rate.overall']),
    retention_rate: num(r['latest.student.retention_rate.four_year.full_time']),
    repayment_rate_3yr: repaymentRate3yr(r),
  }
}

export function mapPrograms(r: ScorecardRow): SchoolProgramRow[] {
  const schoolId = int(r.id)
  const raw = r[PROGRAM_PREFIX]
  if (schoolId === null || !Array.isArray(raw)) return []

  const rows = new Map<string, SchoolProgramRow>()
  for (const item of raw) {
    const p = obj(item)
    const cipCode = str(p.code)
    const level = int(get(p, 'credential.level'))
    if (!cipCode || level === null) continue
    rows.set(`${cipCode}:${level}`, {
      school_id: schoolId,
      cip_code: cipCode,
      title: (str(p.title) ?? cipCode).replace(/\.$/, ''),
      credential_level: level,
      earnings_1yr: int(get(p, 'earnings.1_yr.overall_median_earnings')),
      earnings_4yr: int(get(p, 'earnings.4_yr.overall_median_earnings')),
      median_debt: int(get(p, 'debt.staff_grad_plus.all.eval_inst.median')),
    })
  }
  return [...rows.values()]
}

export async function upsertSchools(prisma: PrismaClient, rows: SchoolRow[]): Promise<void> {
  const now = new Date()
  await prisma.$transaction(
    rows.map((row) =>
      prisma.school.upsert({
        where: { school_id: row.school_id },
        create: { ...row, fetched_at: now },
        update: { ...row, fetched_at: now },
      })
    )
  )
}

/** Replace all programs for the given schools with the fetched rows. */
export async function replacePrograms(
  prisma: PrismaClient,
  schoolIds: number[],
  rows: SchoolProgramRow[]
): Promise<void> {
  const now = new Date()
  await prisma.$transaction([
    prisma.schoolProgram.deleteMany({ where: { school_id: { in: schoolIds } } }),
    prisma.schoolProgram.createMany({
      data: rows.map((row) => ({ ...row, fetched_at: now })),
      skipDuplicates: true,
    }),
  ])
}

/** Runtime fallback: search Scorecard by name/state, persist matches, return them. */
export async function fetchAndStoreSchools(
  prisma: PrismaClient,
  query: { name?: string; state?: string }
): Promise<SchoolRow[]> {
  const page = await fetchSchoolsPage(query, 0, 25)
  const rows = page.results.map(mapSchool).filter((r): r is SchoolRow => r !== null)
  if (rows.length > 0) await upsertSchools(prisma, rows)
  return rows
}

/** Runtime fallback: fetch one school's programs, persist them, return them. */
export async function fetchAndStorePrograms(
  prisma: PrismaClient,
  schoolId: number
): Promise<SchoolProgramRow[]> {
  const exists = await prisma.school.findUnique({ where: { school_id: schoolId }, select: { school_id: true } })
  if (!exists) {
    const schools = await fetchSchoolsPage({ id: schoolId }, 0, 1)
    const rows = schools.results.map(mapSchool).filter((r): r is SchoolRow => r !== null)
    if (rows.length === 0) return []
    await upsertSchools(prisma, rows)
  }

  const page = await fetchProgramsPage({ id: schoolId }, 0, 1)
  const rows = page.results.flatMap(mapPrograms)
  await replacePrograms(prisma, [schoolId], rows)
  return rows
}
