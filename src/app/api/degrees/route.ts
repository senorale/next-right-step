export const dynamic = 'force-dynamic'

import { prisma } from '@/lib/prisma'
import { NextResponse } from 'next/server'

// All degree fields (4-digit CIP codes) with their linked occupation ids.
export async function GET() {
  try {
    const cipCodes = await prisma.cipCode.findMany({
      select: {
        id: true,
        code: true,
        title: true,
        occupations: { select: { occupation_id: true } },
      },
      orderBy: { title: 'asc' },
    })

    return NextResponse.json(
      cipCodes.map((cip) => ({
        id: cip.id,
        code: cip.code,
        name: cip.title.replace(/\.$/, ''),
        occupationIds: cip.occupations.map((o) => o.occupation_id),
      }))
    )
  } catch (error) {
    console.error('Error fetching degrees:', error)
    return NextResponse.json({ error: 'Failed to fetch degrees' }, { status: 500 })
  }
}
