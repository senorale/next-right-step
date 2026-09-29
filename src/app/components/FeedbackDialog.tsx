'use client'

import { useState } from 'react'
import { MessageSquare, X, Send, CheckCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

const CATEGORIES: Record<string, string[]> = {
  app: ['Data accuracy', 'Missing school or program', 'UI/design', 'Feature request', 'Other'],
  agent: ['Response quality', 'Missing or wrong data', 'Too slow', 'Confusing flow', 'Other'],
}

const AREA_LABELS: Record<string, { title: string; description: string }> = {
  app: {
    title: 'The app itself',
    description: 'Data tools, comparisons, landing page',
  },
  agent: {
    title: 'Counselor Agent',
    description: 'Chat experience, advice quality',
  },
}

type Step = 'area' | 'category' | 'message' | 'sent'

export default function FeedbackDialog() {
  const [open, setOpen] = useState(false)
  const [step, setStep] = useState<Step>('area')
  const [area, setArea] = useState('')
  const [category, setCategory] = useState('')
  const [message, setMessage] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')

  function reset() {
    setStep('area')
    setArea('')
    setCategory('')
    setMessage('')
    setError('')
    setSending(false)
  }

  function close() {
    setOpen(false)
    setTimeout(reset, 200)
  }

  function selectArea(a: string) {
    setArea(a)
    setStep('category')
  }

  function selectCategory(c: string) {
    setCategory(c)
    setStep('message')
  }

  async function submit() {
    if (!message.trim() || sending) return
    setSending(true)
    setError('')

    try {
      const res = await fetch('/api/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ area, category, message: message.trim() }),
      })

      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.error || 'Failed to send')
      }

      setStep('sent')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
    } finally {
      setSending(false)
    }
  }

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="fixed top-4 right-4 z-40 flex h-12 w-12 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg transition-transform hover:scale-105"
        aria-label="Send feedback"
      >
        <MessageSquare className="h-5 w-5" />
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex items-end justify-end p-4 sm:items-center sm:justify-center">
          <div className="fixed inset-0 bg-black/40" onClick={close} />
          <div className="relative w-full max-w-md rounded-xl border bg-background shadow-xl">
            <div className="flex items-center justify-between border-b px-4 py-3">
              <h2 className="text-sm font-semibold">Send Feedback</h2>
              <button onClick={close} className="text-muted-foreground hover:text-foreground">
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="p-4">
              {step === 'area' && (
                <div className="space-y-3">
                  <p className="text-sm text-muted-foreground">What is your feedback about?</p>
                  <div className="space-y-2">
                    {Object.entries(AREA_LABELS).map(([key, { title, description }]) => (
                      <button
                        key={key}
                        onClick={() => selectArea(key)}
                        className="w-full rounded-lg border p-3 text-left transition-colors hover:border-primary hover:bg-primary/5"
                      >
                        <div className="text-sm font-medium">{title}</div>
                        <div className="text-xs text-muted-foreground">{description}</div>
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {step === 'category' && (
                <div className="space-y-3">
                  <button
                    onClick={() => { setArea(''); setStep('area') }}
                    className="text-xs text-muted-foreground hover:text-foreground"
                  >
                    ← Back
                  </button>
                  <p className="text-sm text-muted-foreground">What kind of feedback?</p>
                  <div className="flex flex-wrap gap-2">
                    {CATEGORIES[area].map((cat) => (
                      <button
                        key={cat}
                        onClick={() => selectCategory(cat)}
                        className="rounded-full border px-3 py-1.5 text-sm transition-colors hover:border-primary hover:bg-primary/5"
                      >
                        {cat}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {step === 'message' && (
                <div className="space-y-3">
                  <button
                    onClick={() => { setCategory(''); setStep('category') }}
                    className="text-xs text-muted-foreground hover:text-foreground"
                  >
                    ← Back
                  </button>
                  <div className="flex flex-wrap gap-1.5">
                    <span className="rounded-full bg-secondary px-2.5 py-0.5 text-xs">
                      {AREA_LABELS[area].title}
                    </span>
                    <span className="rounded-full bg-secondary px-2.5 py-0.5 text-xs">
                      {category}
                    </span>
                  </div>
                  <textarea
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                    placeholder="Tell us more..."
                    rows={4}
                    maxLength={5000}
                    className="w-full resize-none rounded-lg border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    autoFocus
                  />
                  {error && (
                    <p className="text-sm text-destructive">{error}</p>
                  )}
                  <Button
                    onClick={submit}
                    disabled={!message.trim() || sending}
                    className="w-full gap-2"
                  >
                    <Send className="h-4 w-4" />
                    {sending ? 'Sending...' : 'Send Feedback'}
                  </Button>
                </div>
              )}

              {step === 'sent' && (
                <div className="flex flex-col items-center gap-3 py-4">
                  <CheckCircle className="h-10 w-10 text-green-500" />
                  <p className="text-sm font-medium">Thanks for your feedback!</p>
                  <Button variant="outline" onClick={close} size="sm">
                    Close
                  </Button>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  )
}
