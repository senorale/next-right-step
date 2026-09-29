import type { Metadata } from 'next'
import Link from 'next/link'
import { ChevronDown } from 'lucide-react'
import type { ReactNode } from 'react'
import * as C from '@/app/constants/college_related_constants'

export const metadata: Metadata = {
  title: 'FAQ · Next Right Step',
}

const faqs: { q: string; a: ReactNode }[] = [
  {
    q: 'What is this tool for?',
    a: (
      <>
        It puts real numbers on the trade-off between what college costs and what you can
        expect to earn, so you can decide whether and where to go. It won&apos;t push you
        either way. For many people a trade or apprenticeship is the better answer.
      </>
    ),
  },
  {
    q: 'Why do you use the median instead of the average?',
    a: (
      <>
        The <span className="font-medium text-foreground">median</span> is the middle
        value: half earn more, half earn less. The{' '}
        <span className="font-medium text-foreground">average</span> gets pulled up by a
        few very high earners or expensive schools, so it overstates the typical case.
        Salaries and costs are skewed that way, so we use the national median everywhere.
      </>
    ),
  },
  {
    q: 'Where does the data come from?',
    a: (
      <ul className="list-disc space-y-1.5 pl-4">
        <li>
          <span className="font-medium text-foreground">Salaries:</span>{' '}
          2024 national median annual wages from the{' '}
          <a href="https://www.bls.gov/oes/" target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
            U.S. Bureau of Labor Statistics
          </a>
        </li>
        <li>
          <span className="font-medium text-foreground">School costs and outcomes:</span>{' '}
          Tuition, net price, graduation rates, median debt, and per-program earnings from the{' '}
          <a href="https://collegescorecard.ed.gov/data/" target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
            U.S. Department of Education College Scorecard
          </a>
        </li>
        <li>
          <span className="font-medium text-foreground">Education requirements:</span>{' '}
          Typical years of schooling per occupation from{' '}
          <a href="https://services.onetcenter.org/" target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
            O*NET Web Services
          </a>{' '}
          (U.S. Department of Labor)
        </li>
        <li>
          <span className="font-medium text-foreground">Counselor Agent:</span>{' '}
          AI-powered synthesis of these data sources into personalized guidance
        </li>
      </ul>
    ),
  },
  {
    q: 'How is the pay-off point calculated?',
    a: (
      <>
        We total the cost of the degree (tuition or net price, loan interest, and the
        wages given up while studying), then divide by how much more a graduate earns each
        year than someone with only a high-school diploma. That gives the number of years
        for the higher salary to pay back the investment.
      </>
    ),
  },
  {
    q: 'How do you estimate debt for careers that need a graduate degree?',
    a: (
      <>
        College Scorecard reports debt per credential, so a law or medical degree&apos;s
        median debt only covers money borrowed for that degree. Nobody gets there without a
        bachelor&apos;s first, so for careers that typically need a master&apos;s, doctoral, or
        professional degree we add the national median bachelor&apos;s debt on top. We use
        the national figure (weighted by how many schools report each field) because the
        bachelor&apos;s before a graduate program can be in any field. Your own undergraduate
        debt may be higher or lower.
      </>
    ),
  },
  {
    q: "What's the difference between sticker price and net price?",
    a: (
      <>
        <span className="font-medium text-foreground">Sticker price</span> is{' '}
        <span className="font-medium text-foreground">tuition and fees only</span>, before
        aid, with no living costs.{' '}
        <span className="font-medium text-foreground">Net price</span> is the full cost of
        attendance (tuition plus living) minus average aid, what students actually pay.
        Private schools often have a high sticker but a low net price thanks to heavy
        scholarship discounting; public schools discount less.
      </>
    ),
  },
  {
    q: 'What loan interest rate and repayment plan do you assume?',
    a: (
      <>
        A {C.STUDENT_LOAN_INTEREST_RATE}% rate repaid over {C.TYPICAL_REPAYMENT_YEARS} years.
        The federal standard plan is 10 years, but most borrowers take much longer: the
        average borrower owes about $39,000 and takes up to 20 years to repay, at roughly $200
        to $299 a month (
        <a
          href="https://educationdata.org/student-loan-debt-statistics"
          target="_blank"
          rel="noopener noreferrer"
          className="text-primary hover:underline"
        >
          EducationData.org
        </a>
        ). Check your own terms at{' '}
        <a
          href="https://studentaid.gov/understand-aid/types/loans/interest-rates"
          target="_blank"
          rel="noopener noreferrer"
          className="text-primary hover:underline"
        >
          StudentAid.gov
        </a>
        .
      </>
    ),
  },
  {
    q: 'Is this financial advice?',
    a: (
      <>
        No. These are estimates from national medians and simplifying assumptions. Your
        own costs, aid, salary, and terms will differ. Treat it as a starting point, not a
        guarantee.
      </>
    ),
  },
]

export default function FaqPage() {
  return (
    <main className="flex min-h-screen flex-col items-center p-4 sm:p-6 md:p-16">
      <div className="w-full max-w-2xl space-y-6">
        <div className="space-y-2">
          <Link href="/" className="text-sm text-primary hover:underline">
            ← Back
          </Link>
          <h1 className="text-3xl font-bold tracking-tight">Frequently asked questions</h1>
        </div>

        <div className="space-y-3">
          {faqs.map(({ q, a }) => (
            <details key={q} className="group rounded-lg border bg-card p-4">
              <summary className="flex cursor-pointer list-none items-center justify-between font-medium">
                {q}
                <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-180" />
              </summary>
              <div className="mt-3 text-sm leading-relaxed text-muted-foreground">{a}</div>
            </details>
          ))}
        </div>
      </div>
    </main>
  )
}
