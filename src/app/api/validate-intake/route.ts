export const dynamic = 'force-dynamic'

import { NextRequest, NextResponse } from 'next/server'
import { agentError, postToAgent } from '@/lib/agent-api'

// Checks one free-text intake answer (see api/intake_validation.py).
export async function POST(req: NextRequest) {
  try {
    const res = await postToAgent(req, '/validate-intake', await req.json())
    if (!res.ok) return agentError(res)
    return NextResponse.json(await res.json())
  } catch {
    return NextResponse.json({ error: 'Failed to reach agent API' }, { status: 502 })
  }
}
