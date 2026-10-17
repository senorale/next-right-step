export const dynamic = 'force-dynamic'

import { NextRequest, NextResponse } from 'next/server'
import { agentError, postToAgent } from '@/lib/agent-api'

export async function POST(req: NextRequest) {
  try {
    const res = await postToAgent(req, '/chat', await req.json())

    if (!res.ok) return agentError(res)

    return new Response(res.body, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
      },
    })
  } catch {
    return NextResponse.json(
      { error: 'Failed to reach agent API' },
      { status: 502 }
    )
  }
}
