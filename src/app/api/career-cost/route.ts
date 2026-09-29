export const dynamic = 'force-dynamic'

import { NextRequest, NextResponse } from 'next/server'
import { getCareerCost } from '@/lib/career-cost'

// GET /api/career-cost?occupationId=X  or  ?code=47-2111
export async function GET(request: NextRequest) {
  const id = request.nextUrl.searchParams.get('occupationId')
  const code = request.nextUrl.searchParams.get('code')
  if (!id && !code) {
    return NextResponse.json({ error: 'occupationId or code is required' }, { status: 400 })
  }

  try {
    const result = await getCareerCost(id ? { id } : { occupation_code: code as string })
    if (!result) {
      return NextResponse.json({ error: 'Occupation not found' }, { status: 404 })
    }
    return NextResponse.json(result)
  } catch (error) {
    console.error('Error fetching career cost:', error)
    return NextResponse.json({ error: 'Failed to fetch career cost' }, { status: 500 })
  }
}
