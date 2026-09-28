export const dynamic = 'force-dynamic'

import { NextRequest, NextResponse } from 'next/server'
import { prisma } from '@/lib/prisma'
import { fetchAndStorePrograms } from '@/lib/scorecard'

const STALE_AFTER_MS = 30 * 24 * 60 * 60 * 1000

// GET /api/schools/134130/programs
// Programs load lazily: the first request for a school (or one older than 30
// days) fetches all its programs from the College Scorecard API and stores them.
export async function GET(_request: NextRequest, ctx: RouteContext<'/api/schools/[id]/programs'>) {
  const { id } = await ctx.params
  const schoolId = Number(id)
  if (!Number.isInteger(schoolId) || schoolId <= 0) {
    return NextResponse.json({ error: 'Invalid school id' }, { status: 400 })
  }

  try {
    const newest = await prisma.schoolProgram.findFirst({
      where: { school_id: schoolId },
      orderBy: { fetched_at: 'desc' },
      select: { fetched_at: true },
    })
    let source = 'db'
    if (!newest || Date.now() - newest.fetched_at.getTime() > STALE_AFTER_MS) {
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
          select: { occupation: { select: { id: true, name: true, annual_salary: true } } },
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
        occupations: occupationsByCip.get(p.cip_code) ?? [],
      })),
    })
  } catch (error) {
    console.error('Error fetching school programs:', error)
    return NextResponse.json({ error: 'Failed to fetch school programs' }, { status: 500 })
  }
}
