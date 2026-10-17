export const dynamic = 'force-dynamic'

import { NextRequest, NextResponse } from 'next/server'
import { agentError, postToAgent } from '@/lib/agent-api'

export async function POST(req: NextRequest) {
  try {
    const res = await postToAgent(req, '/retry-report', await req.json())

    if (!res.ok) return agentError(res)

    return NextResponse.json(await res.json())
  } catch {
    return NextResponse.json(
      { error: 'Failed to reach agent API' },
      { status: 502 }
    )
  }
}
