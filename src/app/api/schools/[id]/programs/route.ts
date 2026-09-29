export const dynamic = 'force-dynamic'

import { NextRequest, NextResponse } from 'next/server'
import { prisma } from '@/lib/prisma'
import { fetchAndStorePrograms } from '@/lib/scorecard'

// Approximate years of school for each Scorecard CREDLEV code.
const YEARS_BY_CREDENTIAL: Record<number, number> = { 1: 1, 2: 2, 3: 4, 4: 5, 5: 6, 6: 8, 7: 8, 8: 6 }

/**
 * Occupations a graduate of this credential can typically enter: those whose
 * typical years of school do not exceed the credential's. A nursing bachelor's
 * links to Registered Nurses, not Nurse Anesthetists (a doctorate).
 */
function reachable<T extends { typical_years_of_school: number | null }>(occupations: T[], credentialLevel: number): T[] {
  const years = YEARS_BY_CREDENTIAL[credentialLevel]
  if (years === undefined) return occupations
  return occupations.filter((o) => (o.typical_years_of_school ?? 0) <= years)
}

// GET /api/schools/134130/programs
// Programs load lazily: the first request for a school fetches all its programs
// from the College Scorecard API and stores them. Stored programs are not refetched.
export async function GET(_request: NextRequest, ctx: RouteContext<'/api/schools/[id]/programs'>) {
  const { id } = await ctx.params
  const schoolId = Number(id)
  if (!Number.isInteger(schoolId) || schoolId <= 0) {
    return NextResponse.json({ error: 'Invalid school id' }, { status: 400 })
  }

  try {
    const stored = await prisma.schoolProgram.findFirst({ where: { school_id: schoolId }, select: { id: true } })
    let source = 'db'
    if (!stored) {
      await fetchAndStorePrograms(prisma, schoolId)
      source = 'scorecard'
    }

    const [school, programs] = await Promise.all([
      prisma.school.findUnique({ where: { school_id: schoolId } }),
      prisma.schoolProgram.findMany({
        where: { school_id: schoolId },
        orderBy: [{ title: 'asc' }, { credential_level: 'asc' }],
      }),
    ])
    if (!school) {
      return NextResponse.json({ error: 'School not found' }, { status: 404 })
    }

    // National salary for each program's degree field, via the CIP-SOC crosswalk,
    // and national median debt as a fallback when the school reports none.
    const cips = await prisma.cipCode.findMany({
      where: { code: { in: [...new Set(programs.map((p) => p.cip_code))] } },
      select: {
        code: true,
        occupations: {
          select: {
            occupation: { select: { id: true, name: true, annual_salary: true, typical_years_of_school: true } },
          },
        },
        debt: {
          where: { school_type: 'all' },
          select: { credential_level: true, median_debt: true },
        },
      },
    })
    const nationalDebt = new Map(
      cips.flatMap((c) => c.debt.map((d) => [`${c.code}:${d.credential_level}`, d.median_debt] as const))
    )
    const occupationsByCip = new Map(
      cips.map((c) => [
        c.code,
        c.occupations
          .map((o) => o.occupation)
          .sort((a, b) => b.annual_salary - a.annual_salary),
      ])
    )

    return NextResponse.json({
      school,
      source,
      programs: programs.map((p) => ({
        ...p,
        national_median_debt: nationalDebt.get(`${p.cip_code}:${p.credential_level}`) ?? null,
        occupations: reachable(occupationsByCip.get(p.cip_code) ?? [], p.credential_level),
      })),
    })
  } catch (error) {
    console.error('Error fetching school programs:', error)
    return NextResponse.json({ error: 'Failed to fetch school programs' }, { status: 500 })
  }
}
