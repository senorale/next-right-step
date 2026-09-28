'use client'

import { useEffect, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import * as C from '@/app/constants/college_related_constants'
import PathHeader from '../components/paths/PathHeader'
import OccupationSearch from '../components/paths/OccupationSearch'
import SelectedPills from '../components/paths/SelectedPills'
import ComparisonTable, { bestIndex } from '../components/paths/ComparisonTable'
import BarChartComparison from '../components/paths/BarChartComparison'
import { computeFinancials, HS_SALARY, type Financials } from '../components/paths/finance'
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
    y === 0 ? 'No school required' : `Median debt for a ${c.credentialLabel?.toLowerCase() ?? 'degree'} in related fields`,
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

  useEffect(() => {
    Promise.all([
      fetchCareerCost(`code=${CASHIER_CODE}`),
      fetchCareerCost(`code=${ELECTRICIAN_CODE}`),
      fetch('/api/tuition-medians').then((r) => r.json() as Promise<{ cohort: string; net_price_annual: number | null }[]>),
    ])
      .then(([cashier, electrician, tuition]) => {
        const netPrice = tuition.find((t) => t.cohort === 'all')?.net_price_annual ?? null
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
            netPrice === null ? null : netPrice * BACHELOR_YEARS,
            `National median net price (${netPrice === null ? 'n/a' : money(netPrice)}/yr) x ${BACHELOR_YEARS} years`,
            C.BACHELOR_DEGREE_MEDIAN_SALARY
          )
        )
        setBaselines(options)
      })
      .catch(() => {})
  }, [])

  const choose = async (o: Occupation) => {
    setLoadingChoice(true)
    const cost = await fetchCareerCost(`occupationId=${o.id}`)
    setChosen(cost ? careerOption(cost) : null)
    setLoadingChoice(false)
  }

  const options = chosen ? [...baselines, chosen] : baselines
  const payoffs = options.map((o) => (o.financials && o.yearsInSchool > 0 ? o.financials.payoffYears : null))
  const lifetime = options.map((o) =>
    o.cost === null ? null : o.salary * (CAREER_YEARS - o.yearsInSchool) - o.cost
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
                    info: 'Bachelor\'s median uses the national net price. Careers use median student debt for the typical credential in related fields (College Scorecard).',
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
                    label: 'Opportunity cost',
                    info: `High school median salary (${money(HS_SALARY)}) x years in school.`,
                    values: options.map((o) => moneyOrNA(o.financials?.opportunityCost)),
                  },
                  {
                    label: 'Total investment',
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
                title={`Lifetime earnings over a ${CAREER_YEARS}-year career, minus education cost`}
                data={options.map((o, i) => ({ name: o.name, value: lifetime[i], color: colorAt(i) }))}
                format={(v) => `$${(v / 1_000_000).toFixed(1)}M`}
              />
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
