'use client'

import { useEffect, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import * as C from '@/app/constants/college_related_constants'
import PathHeader from '../components/paths/PathHeader'
import OccupationSearch from '../components/paths/OccupationSearch'
import SelectedPills from '../components/paths/SelectedPills'
import ComparisonTable, { bestIndex } from '../components/paths/ComparisonTable'
import BarChartComparison from '../components/paths/BarChartComparison'
import { computeFinancials, HS_SALARY, LOAN_RATE, REPAYMENT_YEARS, type Financials } from '../components/paths/finance'
import { colorAt, money, moneyOrNA, schoolYears, years } from '../components/paths/format'
import type { CareerCost, Occupation } from '../components/paths/types'

const CAREER_YEARS = 45
const BACHELOR_YEARS = parseFloat(C.BACHELOR_YEARS_IN_SCHOOL)
const CASHIER_CODE = '41-2011'
const ELECTRICIAN_CODE = '47-2111'

interface Option {
  key: string
  name: string
  yearsInSchool: number
  /** null when school is required but no cost data exists */
  cost: number | null
  costSource: string
  salary: number
  financials: Financials | null
}

function toOption(key: string, name: string, yearsInSchool: number, cost: number | null, costSource: string, salary: number): Option {
  return {
    key,
    name,
    yearsInSchool,
    cost,
    costSource,
    salary,
    financials:
      cost === null ? null : computeFinancials({ debt: cost, yearsInSchool, salary, baselineSalary: HS_SALARY }),
  }
}

function careerOption(c: CareerCost): Option {
  const y = c.occupation.typical_years_of_school ?? 0
  return toOption(
    c.occupation.id,
    c.occupation.name,
    y,
    c.totalDebt,
    y === 0
      ? 'No school required'
      : c.debtEstimated
        ? `Estimated from median debt for a ${c.credentialLabel?.toLowerCase() ?? 'degree'} in the broader field family`
        : `Median debt for a ${c.credentialLabel?.toLowerCase() ?? 'degree'} in related fields`,
    c.occupation.annual_salary
  )
}

async function fetchCareerCost(param: string): Promise<CareerCost | null> {
  const r = await fetch(`/api/career-cost?${param}`)
  return r.ok ? r.json() : null
}

export default function CollegeVsAlternatives() {
  const [baselines, setBaselines] = useState<Option[]>([])
  const [chosen, setChosen] = useState<Option | null>(null)
  const [loadingChoice, setLoadingChoice] = useState(false)
  const [loadingBaselines, setLoadingBaselines] = useState(true)

  useEffect(() => {
    Promise.all([
      fetchCareerCost(`code=${CASHIER_CODE}`),
      fetchCareerCost(`code=${ELECTRICIAN_CODE}`),
      fetch('/api/bachelors-debt').then((r) => (r.ok ? (r.json() as Promise<{ median_debt: number }>) : null)),
    ])
      .then(([cashier, electrician, bachelors]) => {
        const bachelorsDebt = bachelors?.median_debt ?? null
        const options: Option[] = [
          toOption('hs', 'High school diploma', 0, 0, 'No school required', HS_SALARY),
        ]
        if (cashier) options.push(careerOption(cashier))
        if (electrician) options.push(careerOption(electrician))
        options.push(
          toOption(
            'bachelors',
            "Bachelor's degree (median)",
            BACHELOR_YEARS,
            bachelorsDebt,
            "National median bachelor's debt across all degree fields",
            C.BACHELOR_DEGREE_MEDIAN_SALARY
          )
        )
        setBaselines(options)
      })
      .catch(() => {})
      .finally(() => setLoadingBaselines(false))
  }, [])

  const choose = async (o: Occupation) => {
    setLoadingChoice(true)
    const cost = await fetchCareerCost(`occupationId=${o.id}`)
    setChosen(cost ? careerOption(cost) : null)
    setLoadingChoice(false)
  }

  const options = chosen ? [...baselines, chosen] : baselines
  const bachelorsPayoff = baselines.find((o) => o.key === 'bachelors')?.financials?.payoffYears ?? null
  const payoffs = options.map((o) => (o.financials && o.yearsInSchool > 0 ? o.financials.payoffYears : null))
  const lifetime = options.map((o) =>
    o.cost === null || !o.financials
      ? null
      : o.salary * (CAREER_YEARS - o.yearsInSchool) - o.cost - o.financials.interest
  )

  return (
    <main className="flex min-h-screen flex-col items-center p-4 sm:p-6 md:p-16">
      <div className="w-full max-w-3xl space-y-6">
        <PathHeader
          title="College vs alternatives"
          description="Compare going to college with trades and working right away. Add a career you're curious about to see how it stacks up."
        />

        <Card>
          <CardHeader>
            <CardTitle className="text-lg">The short answer: it depends</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm leading-relaxed text-muted-foreground">
            <p>
              On the national median, a bachelor&apos;s graduate earns about{' '}
              <span className="font-medium text-foreground">{money(C.BACHELOR_DEGREE_MEDIAN_SALARY)}</span> a year,
              roughly{' '}
              <span className="font-medium text-foreground">{money(C.BACHELOR_DEGREE_MEDIAN_SALARY - HS_SALARY)}</span>{' '}
              more than the {money(HS_SALARY)} typical with only a high school diploma.
              {bachelorsPayoff != null && (
                <>
                  {' '}
                  After debt, interest, and wages given up while in school, the degree pays for itself in about{' '}
                  <span className="whitespace-nowrap font-medium text-foreground">{years(bachelorsPayoff)}</span>.
                </>
              )}
            </p>
            <p>
              That is just the median. What you pay and what your field earns move the answer a lot. College
              isn&apos;t the only path, either: skilled trades and{' '}
              <a
                href="https://www.apprenticeship.gov/"
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary hover:underline"
              >
                registered apprenticeships
              </a>{' '}
              pay you while you learn, with little or no debt.
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Add a career to compare</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <OccupationSearch
              onSelect={choose}
              excludeIds={options.map((o) => o.key)}
              placeholder={chosen ? 'Pick a different career…' : 'Search careers, e.g. nurse, welder…'}
            />
            {chosen && (
              <SelectedPills items={[{ key: chosen.key, label: chosen.name }]} onRemove={() => setChosen(null)} />
            )}
            {loadingChoice && <p className="text-sm text-muted-foreground">Loading…</p>}
          </CardContent>
        </Card>

        {loadingBaselines && <p className="text-center text-sm text-muted-foreground">Loading comparison…</p>}

        {options.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Side by side</CardTitle>
            </CardHeader>
            <CardContent>
              <ComparisonTable
                columns={options.map((o, i) => ({ key: o.key, label: o.name, color: colorAt(i) }))}
                rows={[
                  { label: 'School required', values: options.map((o) => schoolYears(o.yearsInSchool)) },
                  {
                    label: 'Estimated cost',
                    info: "Median student debt at graduation. Bachelor's median uses all degree fields nationally. Careers use the typical credential in related fields (College Scorecard).",
                    values: options.map((o) => (
                      <span key={o.key} title={o.costSource}>
                        {o.cost === null ? 'Cost data unavailable' : money(o.cost)}
                      </span>
                    )),
                  },
                  {
                    label: 'Expected salary',
                    values: options.map((o) => money(o.salary)),
                    best: bestIndex(options.map((o) => o.salary), true),
                  },
                  {
                    label: 'Loan interest',
                    info: `Interest if the full cost is borrowed and repaid over ${REPAYMENT_YEARS} years at ${LOAN_RATE}%.`,
                    values: options.map((o) => moneyOrNA(o.financials?.interest)),
                  },
                  {
                    label: 'Opportunity cost',
                    info: `High school median salary (${money(HS_SALARY)}) x years in school.`,
                    values: options.map((o) => moneyOrNA(o.financials?.opportunityCost)),
                  },
                  {
                    label: 'Total investment',
                    info: 'Estimated cost plus loan interest plus opportunity cost.',
                    values: options.map((o) => moneyOrNA(o.financials?.totalCost)),
                  },
                  {
                    label: 'Payoff timeline',
                    info: 'Years of work until the salary gain over a high school diploma recovers the total investment.',
                    values: options.map((o, i) =>
                      o.yearsInSchool === 0
                        ? 'Nothing to pay off'
                        : !o.financials
                          ? 'n/a'
                          : payoffs[i] === null
                            ? 'Does not pay off'
                            : years(payoffs[i] as number)
                    ),
                    best: bestIndex(payoffs, false),
                  },
                ]}
              />
            </CardContent>
          </Card>
        )}

        {options.length > 0 && (
          <Card>
            <CardContent className="pt-6">
              <BarChartComparison
                title={`Lifetime earnings over a ${CAREER_YEARS}-year career, minus education cost and interest`}
                data={options.map((o, i) => ({ name: o.name, value: lifetime[i], color: colorAt(i) }))}
                format={(v) => `$${(v / 1_000_000).toFixed(1)}M`}
              />
              <p className="mt-4 text-sm text-muted-foreground">
                The path matters more than the diploma. A licensed electrician out-earns the typical high school
                worker with no degree and little debt, while a cashier earns far less. &ldquo;No degree&rdquo; can
                mean very different things.
              </p>
            </CardContent>
          </Card>
        )}

        <p className="text-center text-sm text-muted-foreground">
          Salaries: Bureau of Labor Statistics (May 2024), national medians, capped at $239,200/yr.
          Costs: College Scorecard. Not inflation-adjusted.
        </p>
      </div>
    </main>
  )
}
