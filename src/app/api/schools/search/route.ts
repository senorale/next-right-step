export const dynamic = 'force-dynamic'

import { NextRequest, NextResponse } from 'next/server'
import { prisma } from '@/lib/prisma'
import { fetchAndStoreSchools } from '@/lib/scorecard'

const MAX_RESULTS = 10

// GET /api/schools/search?name=florida&state=FL
// Searches the local School table. With &live=1 and no local match, falls back
// to the College Scorecard API and stores what it finds.
export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams
  const name = params.get('name')?.trim() ?? ''
  const state = params.get('state')?.trim().toUpperCase() ?? ''
  const live = params.get('live') === '1'

  if (name.length < 2 && !state) {
    return NextResponse.json({ error: 'name (2+ chars) or state is required' }, { status: 400 })
  }
  if (state && !/^[A-Z]{2}$/.test(state)) {
    return NextResponse.json({ error: 'state must be a two-letter code' }, { status: 400 })
  }

  try {
    const where = {
      ...(name ? { name: { contains: name, mode: 'insensitive' as const } } : {}),
      ...(state ? { state } : {}),
    }
    const local = await prisma.school.findMany({
      where,
      orderBy: [{ student_size: { sort: 'desc', nulls: 'last' } }, { name: 'asc' }],
      take: MAX_RESULTS,
    })
    if (local.length > 0 || !live) {
      return NextResponse.json({ results: local, source: 'db' })
    }

    await fetchAndStoreSchools(prisma, { name: name || undefined, state: state || undefined })
    const stored = await prisma.school.findMany({
      where,
      orderBy: [{ student_size: { sort: 'desc', nulls: 'last' } }, { name: 'asc' }],
      take: MAX_RESULTS,
    })
    return NextResponse.json({ results: stored, source: 'scorecard' })
  } catch (error) {
    console.error('Error searching schools:', error)
    return NextResponse.json({ error: 'Failed to search schools' }, { status: 500 })
  }
}
