import { NextRequest, NextResponse } from 'next/server'
import { sendFeedbackEmail } from '@/lib/feedback-email'

const VALID_RATINGS = ['up', 'down'] as const
const MAX_TEXT = 5000

function clip(value: unknown, max = MAX_TEXT): string {
  return typeof value === 'string' ? value.trim().slice(0, max) : ''
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json()
    const { rating, details, path_type, question, summary, intake_answers } = body

    if (!VALID_RATINGS.includes(rating)) {
      return NextResponse.json({ error: 'Invalid rating' }, { status: 400 })
    }
    if (details !== undefined && (typeof details !== 'string' || details.length > MAX_TEXT)) {
      return NextResponse.json({ error: 'Invalid details' }, { status: 400 })
    }

    const sentiment = rating === 'up' ? 'Positive' : 'Negative'
    const path = clip(path_type, 20) || 'unknown path'
    const detailText = clip(details)
    const context = [
      `Path: ${path}`,
      '',
      'Question:',
      clip(question) || '(none)',
      '',
      'Chat summary:',
      clip(summary) || '(none)',
      '',
      'Intake answers:',
      JSON.stringify(intake_answers ?? {}, null, 2).slice(0, MAX_TEXT),
    ].join('\n')

    await sendFeedbackEmail({
      areaLabel: 'Counselor Agent',
      category: `Report ${sentiment}`,
      message: detailText || 'Rating only, no details.',
      context,
    })

    return NextResponse.json({ success: true })
  } catch (error) {
    console.error('Report feedback send failed:', error)
    return NextResponse.json({ error: 'Failed to send feedback' }, { status: 500 })
  }
}
