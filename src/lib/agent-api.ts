import { NextRequest, NextResponse } from 'next/server'

const AGENT_API_URL = process.env.AGENT_API_URL || 'http://localhost:8000'

/**
 * The client's IP, which the agent API rate limits on (api/guard.py).
 * Railway's edge sets X-Real-IP; X-Forwarded-For's last entry is the one
 * the edge appended, since a client can put anything in the earlier ones.
 */
function clientIp(req: NextRequest): string | null {
  const real = req.headers.get('x-real-ip')?.trim()
  if (real) return real
  const forwarded = req.headers.get('x-forwarded-for')?.split(',').map((s) => s.trim()).filter(Boolean)
  return forwarded?.at(-1) ?? null
}

/** POSTs a JSON body to the agent API (api/main.py) on behalf of the client. */
export async function postToAgent(req: NextRequest, path: string, body: unknown): Promise<Response> {
  const ip = clientIp(req)
  return fetch(`${AGENT_API_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(ip ? { 'X-Client-IP': ip } : {}) },
    body: JSON.stringify(body),
  })
}

/** The error response for a failed agent API call; a rate limit keeps its message and Retry-After. */
export async function agentError(res: Response): Promise<NextResponse> {
  if (res.status === 429) {
    const detail = await res.json().then((d) => d?.detail).catch(() => null)
    const retryAfter = res.headers.get('retry-after')
    return NextResponse.json(
      { error: detail || 'Too many requests' },
      { status: 429, headers: retryAfter ? { 'Retry-After': retryAfter } : {} }
    )
  }
  return NextResponse.json({ error: 'Agent API error' }, { status: res.status })
}
