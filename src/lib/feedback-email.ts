import { Resend } from 'resend'

const resend = new Resend(process.env.RESEND_API_KEY)
const FEEDBACK_FROM = 'Next Right Step Feedback <onboarding@resend.dev>'
const FEEDBACK_TO = 'alecarvajaldev@gmail.com'

interface FeedbackEmail {
  areaLabel: string
  category: string
  message: string
  // Extra lines appended below the message, e.g. what the user was looking at.
  context?: string
}

export async function sendFeedbackEmail({ areaLabel, category, message, context }: FeedbackEmail) {
  const text = `Area: ${areaLabel}\nCategory: ${category}\n\n${message}${context ? `\n\n---\n${context}` : ''}`
  // The Resend SDK returns API errors instead of throwing them.
  const { data, error } = await resend.emails.send({
    from: FEEDBACK_FROM,
    to: FEEDBACK_TO,
    subject: `[Next Right Step] ${areaLabel} — ${category}`,
    text,
  })
  if (error) throw new Error(`Resend ${error.statusCode ?? ''} ${error.name}: ${error.message}`)
  console.log(`Feedback email sent: id=${data?.id} category=${category}`)
}
