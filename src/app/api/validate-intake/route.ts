export const dynamic = 'force-dynamic'

import { NextRequest, NextResponse } from 'next/server'

const AGENT_API_URL = process.env.AGENT_API_URL || 'http://localhost:8000'

// Checks one free-text intake answer (see api/intake_validation.py).
export async function POST(req: NextRequest) {
  try {
    const res = await fetch(`${AGENT_API_URL}/validate-intake`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(await req.json()),
    })
    if (!res.ok) return NextResponse.json({ error: 'Agent API error' }, { status: res.status })
    return NextResponse.json(await res.json())
  } catch {
    return NextResponse.json({ error: 'Failed to reach agent API' }, { status: 502 })
  }
}
