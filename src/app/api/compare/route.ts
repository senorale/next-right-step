import { prisma } from '@/lib/prisma'
import { NextRequest, NextResponse } from 'next/server'

const CREDENTIAL_YEAR_RANGES: Record<number, [number, number]> = {
  1: [0, 2],
  2: [2, 3],
  3: [3, 5],
  5: [5, 7],
  6: [7, 9],
  7: [8, 12],
  8: [5, 7],
}

function bestCredentialLevel(weightedYears: number): number {
  let best = 3
  let bestDist = Infinity
  for (const [level, [lo, hi]] of Object.entries(CREDENTIAL_YEAR_RANGES)) {
    const mid = (lo + hi) / 2
    const dist = Math.abs(weightedYears - mid)
    if (dist < bestDist) {
      bestDist = dist
      best = Number(level)
    }
  }
  return best
}

export async function GET(request: NextRequest) {
  const cipId = request.nextUrl.searchParams.get('majorId')
  if (!cipId) {
    return NextResponse.json({ error: 'majorId is required' }, { status: 400 })
  }

  try {
    const cip = await prisma.cipCode.findUnique({
      where: { id: cipId },
      select: {
        id: true,
        title: true,
        occupations: {
          select: {
            occupation: {
              select: {
                annual_salary: true,
                typical_years_of_school: true,
              },
            },
          },
        },
        debt: {
          select: {
            credential_level: true,
            credential_label: true,
            school_type: true,
            median_debt: true,
            mean_debt: true,
            sample_size: true,
          },
        },
      },
    })

    if (!cip) {
      return NextResponse.json({ error: 'Field of study not found' }, { status: 404 })
    }

    const count = cip.occupations.length
    const weightedSalary =
      count > 0
        ? cip.occupations.reduce((s, o) => s + o.occupation.annual_salary, 0) / count
        : 0

    const weightedYears =
      count > 0
        ? cip.occupations.reduce(
            (s, o) => s + (o.occupation.typical_years_of_school ?? 4),
            0
          ) / count
        : 4

    const targetLevel = bestCredentialLevel(weightedYears)
    const debtForLevel = cip.debt.filter((d) => d.credential_level === targetLevel)

    let debt: { credentialLevel: number; credentialLabel: string; public: number | null; privateNonprofit: number | null; all: number | null; sampleSize: number } | null = null
    if (debtForLevel.length > 0) {
      const pub = debtForLevel.find((d) => d.school_type === 'public')
      const priv = debtForLevel.find((d) => d.school_type === 'private_nonprofit')
      const all = debtForLevel.find((d) => d.school_type === 'all')
      debt = {
        credentialLevel: targetLevel,
        credentialLabel: debtForLevel[0].credential_label,
        public: pub?.median_debt ?? null,
        privateNonprofit: priv?.median_debt ?? null,
        all: all?.median_debt ?? null,
        sampleSize: all?.sample_size ?? pub?.sample_size ?? priv?.sample_size ?? 0,
      }
    }

    const allDebtLevels = [...new Set(cip.debt.map((d) => d.credential_level))].sort()

    return NextResponse.json({
      degree: { id: cip.id, name: cip.title },
      weightedSalary: Math.round(weightedSalary),
      weightedYears: Math.round(weightedYears * 10) / 10,
      debt,
      availableCredentialLevels: allDebtLevels,
    })
  } catch (error) {
    console.error('Error fetching comparison data:', error)
    return NextResponse.json({ error: 'Failed to fetch comparison data' }, { status: 500 })
  }
}
