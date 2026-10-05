import type { Metadata } from 'next'
import Link from 'next/link'
import { ChevronDown } from 'lucide-react'
import type { ReactNode } from 'react'
import * as C from '@/app/constants/college_related_constants'

export const metadata: Metadata = {
  title: 'FAQ · Next Right Step',
}

const linkClass = 'text-primary hover:underline'
const Strong = ({ children }: { children: ReactNode }) => (
  <span className="font-medium text-foreground">{children}</span>
)
const Ext = ({ href, children }: { href: string; children: ReactNode }) => (
  <a href={href} target="_blank" rel="noopener noreferrer" className={linkClass}>
    {children}
  </a>
)

const faqs: { q: string; a: ReactNode }[] = [
  {
    q: 'Who are we?',
    a: (
      <>
        We&apos;re software engineers who are passionate about democratizing access to information. All of the
        data on this site is public and has been for many years. We just don&apos;t think it&apos;s compiled and
        presented in a useful way anywhere else.
      </>
    ),
  },
  {
    q: 'What is this tool for?',
    a: (
      <div className="space-y-2">
        <p>
          It&apos;s for people trying to figure out their next right step: college, a trade, a new career, or
          staying put. We want to empower you with unbiased, government-issued data so you can make the decision
          yourself. We don&apos;t push you toward college or away from it.
        </p>
        <p>
          There are two ways to use it. The <Strong>guided experience</Strong> is an AI counselor that asks about
          your situation and builds a personalized report. <Strong>Explore on your own</Strong> has five paths:
          college vs alternatives, compare schools, compare programs, compare careers, and path to a career.
        </p>
      </div>
    ),
  },
  {
    q: 'Where does the data come from?',
    a: (
      <div className="space-y-2">
        <p>Every number comes from a U.S. government source:</p>
        <ul className="list-disc space-y-1.5 pl-4">
          <li>
            <Strong>Salaries:</Strong> national median annual wages by occupation from the{' '}
            <Ext href="https://www.bls.gov/oes/">U.S. Bureau of Labor Statistics</Ext> Occupational Employment and
            Wage Statistics, May 2024.
          </li>
          <li>
            <Strong>Schools:</Strong> net price by family income, graduation and retention rates, median debt,
            earnings 10 years after entry, admission rate, and loan repayment from the{' '}
            <Ext href="https://collegescorecard.ed.gov/data/">U.S. Department of Education College Scorecard</Ext>.
            Schools that mainly award bachelor&apos;s degrees are loaded ahead of time. Others are looked up in
            Scorecard the first time someone searches for them, then saved.
          </li>
          <li>
            <Strong>Programs at a school:</Strong> earnings 1 and 4 years after graduation and median debt for each
            program, from College Scorecard, fetched the first time someone opens that school.
          </li>
          <li>
            <Strong>Debt by degree field:</Strong> median debt at graduation for each field and credential level,
            combined across every school that reports it, from the College Scorecard Field of Study data.
          </li>
          <li>
            <Strong>Degrees to careers:</Strong> which degree fields lead to which occupations, from the{' '}
            <Ext href="https://nces.ed.gov/ipeds/cipcode/resources.aspx?y=56">
              National Center for Education Statistics CIP-SOC crosswalk
            </Ext>{' '}
            (2020 degree codes to 2018 occupation codes).
          </li>
          <li>
            <Strong>Years of school per career:</Strong> the most common education level for each occupation from{' '}
            <Ext href="https://services.onetcenter.org/">O*NET Web Services</Ext> (U.S. Department of Labor,
            USDOL/ETA).
          </li>
          <li>
            <Strong>Guided experience:</Strong> an AI counselor (Claude, by Anthropic) that pulls from the same data
            above. It doesn&apos;t use outside sources for its numbers.
          </li>
        </ul>
      </div>
    ),
  },
  {
    q: 'How is this different from other AI tools like ChatGPT?',
    a: (
      <>
        General AI tools could find this data, but you&apos;d have to tell them where to look and how to combine it across
        sources. We&apos;ve organized public government data (BLS, College Scorecard, NCES, O*NET) into our own
        database. The AI looks up exact figures there instead of searching the web, and all the financial math is
        done by code, not the AI.
      </>
    ),
  },
  {
    q: 'How do you link degrees to careers?',
    a: (
      <>
        Through the NCES crosswalk, which maps each degree field to the occupations it prepares you for. A field
        often leads to several jobs, and a job can be reached from several fields. On the pages,{' '}
        <Strong>related degrees</Strong> are the fields the crosswalk links to that career. When we list related
        jobs for a program, we only include ones that program&apos;s credential typically leads to: a nursing
        bachelor&apos;s shows Registered Nurses, not Nurse Anesthetists, which needs a doctorate.
      </>
    ),
  },
  {
    q: 'How many years of school does a career take?',
    a: (
      <div className="space-y-2">
        <p>
          We use the most common education level O*NET reports for that occupation: 0 years for a high school
          diploma or certificate, 2 for an associate&apos;s, 4 for a bachelor&apos;s, 6 for a master&apos;s, and
          8 for a doctoral or professional degree. It&apos;s what most people in the job have, not a hard
          requirement.
        </p>
        <p>
          On <Strong>Path to a career</Strong>, we credit school you&apos;ve already done. If your field is
          related to the career, all your years count. If it isn&apos;t, up to 2 years count (roughly the general
          education credits that transfer), or up to 4 for careers that need a graduate degree, since law,
          medical, and most master&apos;s programs accept a bachelor&apos;s in any field.
        </p>
      </div>
    ),
  },
  {
    q: 'Why do you use median debt instead of tuition?',
    a: (
      <div className="space-y-2">
        <p>
          Tuition, and even net price, is what a school charges. Debt is what students actually borrow and have to
          pay back after grants, scholarships, family help, and work. That&apos;s the number that follows you
          after graduation, so it&apos;s the fairest measure of what the education costs you.
        </p>
        <p>
          College Scorecard also reports debt for each degree field and credential level, so we can estimate the
          cost of a specific career path (a nursing bachelor&apos;s, a law degree) rather than one national tuition
          figure. The careers and the bachelor&apos;s baseline all use median debt, so they compare like with like.
        </p>
        <p>
          The one exception is <Strong>Compare schools</Strong>, which uses each school&apos;s net price for your
          family income times the years of school, because that&apos;s the school-specific figure. It assumes you
          borrow the whole amount, so it&apos;s the more cautious estimate.
        </p>
      </div>
    ),
  },
  {
    q: 'How is the payoff timeline calculated?',
    a: (
      <div className="space-y-2">
        <p>We add up three costs:</p>
        <ul className="list-disc space-y-1 pl-4">
          <li>Education debt (see above)</li>
          <li>
            Loan interest on that debt at {C.STUDENT_LOAN_INTEREST_RATE}% over {C.TYPICAL_REPAYMENT_YEARS} years
          </li>
          <li>
            Wages you give up while in school: your starting salary times the years of school. We assume you study
            full time and earn nothing in the meantime.
          </li>
        </ul>
        <p>
          Then we divide the total by how much more you&apos;d earn each year than your starting salary, and add
          the years of school. The result counts from your first day of school until the higher salary has paid back
          the investment. It assumes you earn the median salary right after graduating; starting pay is often lower,
          so the real payoff usually takes longer.{' '}
          <Strong>Does not pay off</Strong> means the new salary isn&apos;t higher than where you start.{' '}
          <Strong>Nothing to pay off</Strong> means no school is needed.
        </p>
      </div>
    ),
  },
  {
    q: "What does 'Where are you starting from?' change?",
    a: (
      <>
        It sets the salary everything is compared against: the yearly gain, the wages you give up while in school,
        and so the payoff timeline. The default is the {`$${C.HIGHSCHOOL_DIPLOMA_MEDIAN_SALARY.toLocaleString()}`}{' '}
        national median for a high school diploma, which fits most students. If you&apos;re already working, enter
        your salary or pick your current job. A career changer earning $70,000 gives up more while studying and
        gains less afterward, so the payoff takes much longer.
      </>
    ),
  },
  {
    q: 'How many years does Compare schools assume?',
    a: (
      <>
        It depends on what the school mostly awards, per College Scorecard: 1 year for certificate schools, 2 for
        schools that mostly award associate&apos;s degrees, and 4 for everything else.
      </>
    ),
  },
  {
    q: "Why does a cost say 'estimated' or 'Cost data unavailable'?",
    a: (
      <>
        Some degree fields have too few schools reporting debt for College Scorecard to publish a number. When none
        of a career&apos;s related fields have data, we estimate from the broader field family (for example, all
        social sciences) at the same credential level, and label it <Strong>estimated</Strong>. Estimates for
        doctoral degrees can run high, because many PhDs are funded while professional degrees in the same family
        are not. When even the broader family has no data, we show <Strong>Cost data unavailable</Strong>.
      </>
    ),
  },
  {
    q: 'How do you estimate debt for careers that need a graduate degree?',
    a: (
      <>
        College Scorecard reports debt per credential, so a law or medical degree&apos;s median debt only covers
        money borrowed for that degree. Nobody gets there without a bachelor&apos;s first, so for careers that
        typically need a master&apos;s, doctoral, or professional degree we add the national median bachelor&apos;s
        debt on top. We use the national figure (weighted by how many schools report each field) because the
        bachelor&apos;s before a graduate program can be in any field. Your own undergraduate debt may be higher
        or lower.
      </>
    ),
  },
  {
    q: 'What is net price?',
    a: (
      <>
        Net price is the full cost of attendance (tuition, fees, housing, food, books) minus the average grants and
        scholarships students receive. It&apos;s what students actually pay, and it depends heavily on family
        income, which is why Compare schools lets you pick an income range. It&apos;s usually far below the
        advertised sticker price, especially at private schools that discount heavily.
      </>
    ),
  },
  {
    q: 'What loan interest rate and repayment plan do you assume?',
    a: (
      <>
        A {C.STUDENT_LOAN_INTEREST_RATE}% rate repaid over {C.TYPICAL_REPAYMENT_YEARS} years. The federal standard
        plan is 10 years, but most borrowers take much longer: the average borrower owes about $39,000 and takes up
        to 20 years to repay, at roughly $200 to $299 a month (
        <Ext href="https://educationdata.org/student-loan-debt-statistics">EducationData.org</Ext>). Check your own
        terms at <Ext href="https://studentaid.gov/understand-aid/types/loans/interest-rates">StudentAid.gov</Ext>.
      </>
    ),
  },
  {
    q: 'Are the numbers adjusted for inflation? Are salaries capped?',
    a: (
      <>
        No inflation adjustment: all figures are in the dollars of the year each source reports (BLS wages from May
        2024, the latest College Scorecard release). BLS does not publish exact wages above $239,200 a year, so the
        highest-paid occupations show that capped figure.
      </>
    ),
  },
  {
    q: "Why can't I find my school?",
    a: (
      <>
        School names come from the U.S. Department of Education, so search with full words rather than
        abbreviations: &ldquo;Santa Barbara&rdquo; or &ldquo;University of California&rdquo;, not &ldquo;UCSB&rdquo;
        or &ldquo;UC Santa Barbara&rdquo;. Use the state filter to narrow results. If a school isn&apos;t in our
        list yet, choose <Strong>Search College Scorecard</Strong> and we&apos;ll look it up and save it. Schools
        that were renamed appear under their current name.
      </>
    ),
  },
  {
    q: 'Why do you use the median instead of the average?',
    a: (
      <>
        The <Strong>median</Strong> is the middle value: half earn more, half earn less. The{' '}
        <Strong>average</Strong> gets pulled up by a few very high earners or expensive schools, so it overstates
        the typical case. Salaries and costs are skewed that way, so we use medians throughout.
      </>
    ),
  },
  {
    q: 'Is this financial advice?',
    a: (
      <>
        No. These are estimates from national medians and simplifying assumptions. Your own costs, aid, salary, and
        terms will differ. Treat it as a starting point, not a guarantee.
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
