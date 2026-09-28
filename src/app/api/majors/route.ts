export const dynamic = 'force-dynamic'

import { prisma } from '@/lib/prisma'
import { NextResponse } from 'next/server'

export async function GET() {
  try {
    const cipCodes = await prisma.cipCode.findMany({
      select: {
        id: true,
        code: true,
        title: true,
        occupations: {
          select: {
            occupation: {
              select: {
                id: true,
                name: true,
                annual_salary: true,
                typical_years_of_school: true,
              },
            },
          },
        },
      },
      orderBy: { title: 'asc' },
    })

    const result = cipCodes.map((cip) => ({
      id: cip.id,
      name: cip.title,
      code: cip.code,
      occupations: cip.occupations.map((link) => ({
        relevance: 1,
        occupation: link.occupation,
      })),
    }))

    return NextResponse.json(result)
  } catch (error) {
    console.error('Error fetching majors:', error)
    return NextResponse.json({ error: 'Failed to fetch majors' }, { status: 500 })
  }
}
