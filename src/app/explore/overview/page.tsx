import Link from 'next/link'
import MedianPayoffWidget from '../../components/landing/MedianPayoffWidget'
import TradeEarningsComparison from '../../components/landing/TradeEarningsComparison'
import LandingDisclaimer from '../../components/landing/LandingDisclaimer'
import CollapsibleCard from '../../components/landing/CollapsibleCard'
import { Button } from '@/components/ui/button'
import { prisma } from '@/lib/prisma'
import { calculateTotalInterestPaid, calculateBreakEvenYears } from '../../utils'
import * as CollegeConstants from '@/app/constants/college_related_constants'

const TWITTER_LINK = 'https://x.com/mike_branc'
const ALE_LINKED_IN = 'https://www.linkedin.com/in/alejandro-carvajal-916b55190/'
const APPRENTICESHIP_LINK = 'https://www.apprenticeship.gov/'

const HS_SALARY = CollegeConstants.HIGHSCHOOL_DIPLOMA_MEDIAN_SALARY
const GRAD_SALARY = CollegeConstants.BACHELOR_DEGREE_MEDIAN_SALARY
const YEARS = parseFloat(CollegeConstants.BACHELOR_YEARS_IN_SCHOOL)
const RATE = parseFloat(CollegeConstants.STUDENT_LOAN_INTEREST_RATE)

const money = (n: number) => `$${Math.round(n).toLocaleString()}`

// Compute the median headline numbers server-side from the DB so the copy can
// never drift from the real data.
async function getHeadline() {
  try {
    const all = await prisma.tuitionMedian.findUnique({ where: { cohort: 'all' } })
    const annual = all?.net_price_annual ?? all?.sticker_annual
    if (!annual) return null

    const tuition = annual * YEARS
    const interest = calculateTotalInterestPaid(tuition, RATE, 10)
    const total = tuition + interest + HS_SALARY * YEARS
    const breakEven = calculateBreakEvenYears(total, GRAD_SALARY, HS_SALARY)

    return {
      gap: GRAD_SALARY - HS_SALARY,
      breakEven: typeof breakEven === 'number' ? Math.round(breakEven * 10) / 10 : null,
      // Cost of school only (median net price × years) — NOT total loan repayment
      // with interest, which varies by how much is borrowed and the plan.
      // Opportunity cost is excluded too: the lifetime chart captures it via
      // fewer working years.
      degreeCost: tuition,
    }
  } catch {
    return null
  }
}

export default async function Home() {
  const headline = await getHeadline()

  return (
    <main className="flex min-h-screen flex-col items-center p-4 sm:p-6 md:p-16">
      <div className="w-full max-w-2xl space-y-10">
        <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-center text-balance">
          Should I go to college?
        </h1>

        {/* Collapsible drawers */}
        <div className="space-y-3">
        {/* Thesis */}
        <CollapsibleCard title="The short answer" subtitle="It depends">
          <div className="space-y-4 text-muted-foreground leading-relaxed text-pretty">
            <p>
              On the national median, a bachelor&apos;s graduate earns about{' '}
              <span className="font-medium text-foreground">{money(GRAD_SALARY)}</span> a
              year, roughly{' '}
              <span className="font-medium text-foreground">
                {headline ? money(headline.gap) : money(GRAD_SALARY - HS_SALARY)}
              </span>{' '}
              more than the {money(HS_SALARY)} typical with only a high-school diploma.
            </p>
            <p>
              {headline?.breakEven != null && (
                <>
                  After tuition, interest, and lost wages, that degree pays for itself in
                  about{' '}
                  <span className="font-medium text-foreground whitespace-nowrap">
                    {headline.breakEven} years
                  </span>
                  .{' '}
                </>
              )}
              But that&apos;s just the national median. What you pay and what your
              profession earns move the answer a lot. College isn&apos;t the only path, either: skilled
              trades and{' '}
              <a
                href={APPRENTICESHIP_LINK}
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary hover:underline"
              >
                registered apprenticeships
              </a>{' '}
              pay you while you learn, with little or no debt.
            </p>
            <p className="font-medium text-foreground">
              This tool is here to help you decide for yourself, not to push you one way or
              the other.
            </p>
          </div>
        </CollapsibleCard>

        {/* Lifetime earnings: degree vs. trades */}
        <CollapsibleCard title="Lifetime earnings comparison">
          <TradeEarningsComparison degreeCost={headline?.degreeCost ?? 0} />
        </CollapsibleCard>

        {/* Median payoff widget (school-type comparison) */}
        <CollapsibleCard
          title="When does it pay off?"
          subtitle="Depends on how much you owe, how much you earn, and how quickly you repay a loan."
        >
          <MedianPayoffWidget />
        </CollapsibleCard>
        </div>

        {/* CTA to the tools */}
        <section className="space-y-4">
          <h2 className="text-xl font-semibold text-center">Want to learn more?</h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <ToolCard
              href="/compare"
              title="Degree payoff"
              body="Compare debt, salary, and break-even across degrees and programs."
            />
            <ToolCard
              href="/occupations"
              title="Compare occupations"
              body="Already committed to your major? Compare occupation salaries."
            />
            <ToolCard
              href="https://collegescorecard.ed.gov/"
              external
              cta="Open Scorecard"
              title="Compare schools"
              body="Pick a school on the U.S. Dept. of Education College Scorecard: graduation rates, costs, and earnings."
            />
            <ToolCard
              href="/chat"
              cta="Start"
              title="Counselor Agent"
              body="Get personalized advice from an AI agent with access to real salary, tuition, and career data."
            />
          </div>
        </section>

        <p className="text-center text-sm text-muted-foreground">
          Curious how these numbers are calculated, what the assumptions are, or where the
          data comes from?{' '}
          <Link href="/faq" className="text-primary hover:underline">
            Read the FAQ →
          </Link>
        </p>

        <p className="text-center text-sm text-muted-foreground">
          Created by{' '}
          <a
            href={TWITTER_LINK}
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary hover:underline"
          >
            Michael Branconier
          </a>{' '}
          &{' '}
          <a
            href={ALE_LINKED_IN}
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary hover:underline"
          >
            Alejandro Carvajal
          </a>
        </p>

        <LandingDisclaimer />
      </div>
    </main>
  )
}

function ToolCard({
  href,
  title,
  body,
  external,
  cta = 'Open',
}: {
  href: string
  title: string
  body: string
  external?: boolean
  cta?: string
}) {
  const className =
    'flex flex-col rounded-lg border p-5 hover:border-primary hover:shadow-sm transition-colors'
  const inner = (
    <>
      <span className="text-lg font-semibold">{title}</span>
      <span className="text-sm text-muted-foreground mt-1 flex-1">{body}</span>
      <span className="mt-3">
        <Button size="sm" className="pointer-events-none">
          {cta}
        </Button>
      </span>
    </>
  )

  return external ? (
    <a href={href} target="_blank" rel="noopener noreferrer" className={className}>
      {inner}
    </a>
  ) : (
    <Link href={href} className={className}>
      {inner}
    </Link>
  )
}
