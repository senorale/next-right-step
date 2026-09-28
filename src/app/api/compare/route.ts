import { prisma } from '@/lib/prisma'
import { NextRequest, NextResponse } from 'next/server'

export async function GET(request: NextRequest) {
  const cipId = request.nextUrl.searchParams.get('majorId')
  if (!cipId) {
    return NextResponse.json({ error: 'majorId is required' }, { status: 400 })
  }

  try {
    const [cip, medians] = await Promise.all([
      prisma.cipCode.findUnique({
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
        },
      }),
      prisma.tuitionMedian.findMany({
        where: { cohort: { in: ['public_in_state', 'private_nonprofit'] } },
        select: {
          cohort: true,
          label: true,
          sticker_annual: true,
          net_price_annual: true,
        },
      }),
    ])

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

    const publicInState = medians.find((m) => m.cohort === 'public_in_state')
    const privateNonprofit = medians.find((m) => m.cohort === 'private_nonprofit')

    return NextResponse.json({
      major: { id: cip.id, name: cip.title },
      weightedSalary: Math.round(weightedSalary),
      weightedYears: Math.round(weightedYears * 10) / 10,
      tuition: {
        publicInState: publicInState?.net_price_annual ?? publicInState?.sticker_annual ?? 0,
        privateNonprofit: privateNonprofit?.net_price_annual ?? privateNonprofit?.sticker_annual ?? 0,
      },
    })
  } catch (error) {
    console.error('Error fetching comparison data:', error)
    return NextResponse.json({ error: 'Failed to fetch comparison data' }, { status: 500 })
  }
}
