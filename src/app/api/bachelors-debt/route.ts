export const dynamic = 'force-dynamic'

import { NextResponse } from 'next/server'
import { nationalBachelorsDebt } from '@/lib/career-cost'

// GET /api/bachelors-debt
// National median bachelor's debt across all degree fields, weighted by number
// of schools reporting. Source: College Scorecard via ProgramDebt.
export async function GET() {
  try {
    return NextResponse.json({ median_debt: await nationalBachelorsDebt() })
  } catch (error) {
    console.error("Error fetching national bachelor's debt:", error)
    return NextResponse.json({ error: "Failed to fetch national bachelor's debt" }, { status: 500 })
  }
}
