'use client'

import { useState } from 'react'
import { ThumbsUp, ThumbsDown } from 'lucide-react'
import { cn } from '@/lib/utils'

type Rating = 'up' | 'down'

interface ReportFeedbackProps {
  question: string
  summary: string
  intakeAnswers: Record<string, string>
}

export default function ReportFeedback({ question, summary, intakeAnswers }: ReportFeedbackProps) {
  const [rating, setRating] = useState<Rating | null>(null)
  const [sent, setSent] = useState(false)
  const [details, setDetails] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')

  async function send() {
    if (!rating || sending) return
    setSending(true)
    setError('')
    try {
      const res = await fetch('/api/report-feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          rating,
          details: details.trim() || undefined,
          path_type: intakeAnswers.path_type,
          question,
          summary,
          intake_answers: intakeAnswers,
        }),
      })
      if (!res.ok) throw new Error(`Server error: ${res.status}`)
      setSent(true)
    } catch (err) {
      console.error('Report feedback failed:', err)
      setError('Could not send. Try again.')
    } finally {
      setSending(false)
    }
  }

  if (sent) {
    return <p className="text-xs text-muted-foreground">Thanks! This helps us improve the counselor.</p>
  }

  return (
    <div className="w-full max-w-sm space-y-2 text-xs text-muted-foreground">
      <div className="flex items-center gap-2">
        <span>Was this report helpful?</span>
        {(['up', 'down'] as const).map((r) => {
          const Icon = r === 'up' ? ThumbsUp : ThumbsDown
          return (
            <button
              key={r}
              onClick={() => setRating(r)}
              disabled={sending}
              aria-label={r === 'up' ? 'Helpful' : 'Not helpful'}
              aria-pressed={rating === r}
              className={cn(
                'rounded-md p-1.5 transition-colors hover:bg-secondary disabled:cursor-default',
                rating === r ? 'text-primary' : rating && 'opacity-40'
              )}
            >
              <Icon className={cn('h-4 w-4', rating === r && 'fill-current')} />
            </button>
          )
        })}
      </div>

      {rating && (
        <div className="space-y-2">
          <textarea
            value={details}
            onChange={(e) => setDetails(e.target.value)}
            placeholder={rating === 'down' ? 'What was wrong or missing? (optional)' : 'What was most useful? (optional)'}
            maxLength={5000}
            rows={3}
            className="w-full resize-none rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
          <button
            onClick={send}
            disabled={sending}
            className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground disabled:opacity-50"
          >
            {sending ? 'Sending…' : 'Send'}
          </button>
        </div>
      )}

      {error && <p className="text-destructive">{error}</p>}
    </div>
  )
}
