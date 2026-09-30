import { NextRequest, NextResponse } from 'next/server'
import { sendFeedbackEmail } from '@/lib/feedback-email'

const VALID_AREAS = ['app', 'agent'] as const
const VALID_CATEGORIES: Record<string, string[]> = {
  app: ['Data accuracy', 'Missing school or program', 'UI/design', 'Feature request', 'Other'],
  agent: ['Response quality', 'Missing or wrong data', 'Too slow', 'Confusing flow', 'Other'],
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json()
    const { area, category, message } = body

    if (!area || !VALID_AREAS.includes(area)) {
      return NextResponse.json({ error: 'Invalid area' }, { status: 400 })
    }
    if (!category || !VALID_CATEGORIES[area].includes(category)) {
      return NextResponse.json({ error: 'Invalid category' }, { status: 400 })
    }
    if (!message || typeof message !== 'string' || message.trim().length === 0) {
      return NextResponse.json({ error: 'Message required' }, { status: 400 })
    }
    if (message.length > 5000) {
      return NextResponse.json({ error: 'Message too long' }, { status: 400 })
    }

    const areaLabel = area === 'app' ? 'Base App' : 'Counselor Agent'
    await sendFeedbackEmail({ areaLabel, category, message: message.trim() })

    return NextResponse.json({ success: true })
  } catch (error) {
    console.error('Feedback send failed:', error)
    return NextResponse.json({ error: 'Failed to send feedback' }, { status: 500 })
  }
}
