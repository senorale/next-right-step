'use client'

import { useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import PathHeader from '../components/paths/PathHeader'
import MoreDetails from '../components/paths/MoreDetails'
import OccupationSearch from '../components/paths/OccupationSearch'
import SelectedPills from '../components/paths/SelectedPills'
import ComparisonTable, { bestIndex } from '../components/paths/ComparisonTable'
import BarChartComparison from '../components/paths/BarChartComparison'
import BaselinePicker, { baselineLabel, baselineSalary, type Baseline } from '../components/paths/BaselinePicker'
import { computeFinancials, LOAN_RATE, PAYOFF_EXPLAINER, REPAYMENT_YEARS } from '../components/paths/finance'
import { colorAt, money, moneyOrNA, schoolYears, years } from '../components/paths/format'
import type { CareerCost, Occupation } from '../components/paths/types'

const MAX_CAREERS = 5

export default function CompareCareers() {
  const [baseline, setBaseline] = useState<Baseline>({ kind: 'hs' })
  const [careers, setCareers] = useState<CareerCost[]>([])
  const [loading, setLoading] = useState(false)

  const addCareer = async (o: Occupation) => {
    setLoading(true)
    const r = await fetch(`/api/career-cost?occupationId=${o.id}`)
    if (r.ok) {
      const cost: CareerCost = await r.json()
      setCareers((prev) => (prev.length < MAX_CAREERS ? [...prev, cost] : prev))
    }
    setLoading(false)
  }
  const removeCareer = (id: string) => setCareers((prev) => prev.filter((c) => c.occupation.id !== id))

  const base = baselineSalary(baseline)
  const baseName = baselineLabel(baseline)
  const rows = careers.map((c) => {
    const yearsInSchool = c.occupation.typical_years_of_school ?? 0
    const salary = c.occupation.annual_salary
    return {
      c,
      yearsInSchool,
      salary,
      financials:
        c.totalDebt === null ? null : computeFinancials({ debt: c.totalDebt, yearsInSchool, salary, baselineSalary: base }),
    }
  })
  const payoffs = rows.map((r) => r.financials?.payoffYears ?? null)
  const atMax = careers.length >= MAX_CAREERS

  return (
    <main className="flex min-h-screen flex-col items-center p-4 sm:p-6 md:p-16">
      <div className="w-full max-w-3xl space-y-6">
        <PathHeader
          title="Compare careers"
          description="Put career paths side by side: what they pay, what the education costs, and how long until the switch pays off from where you are now."
        />

        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Where are you starting from?</CardTitle>
          </CardHeader>
          <CardContent>
            <BaselinePicker value={baseline} onChange={setBaseline} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-lg">
              Careers to compare{' '}
              <span className="text-sm font-normal text-muted-foreground">
                ({careers.length}/{MAX_CAREERS})
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <OccupationSearch
              onSelect={addCareer}
              excludeIds={careers.map((c) => c.occupation.id)}
              disabled={atMax}
              placeholder={atMax ? 'Remove one to add another' : 'Search careers…'}
            />
            {careers.length > 0 ? (
              <SelectedPills
                items={careers.map((c) => ({ key: c.occupation.id, label: c.occupation.name }))}
                onRemove={removeCareer}
              />
            ) : (
              <p className="text-sm text-muted-foreground">Add up to {MAX_CAREERS} careers.</p>
            )}
            {loading && <p className="text-sm text-muted-foreground">Loading…</p>}
          </CardContent>
        </Card>

        {rows.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Side by side</CardTitle>
            </CardHeader>
            <CardContent>
              <ComparisonTable
                columns={rows.map((r, i) => ({ key: r.c.occupation.id, label: r.c.occupation.name, color: colorAt(i) }))}
                rows={[
                  {
                    label: 'Salary',
                    values: rows.map((r) => money(r.salary)),
                    best: bestIndex(rows.map((r) => r.salary), true),
                  },
                  {
                    label: 'Gain vs starting point',
                    info: `Salary minus ${baseName} (${money(base)}/yr).`,
                    values: rows.map((r) => {
                      const d = r.salary - base
                      return `${d >= 0 ? '+' : '-'}${money(Math.abs(d))}`
                    }),
                  },
                  { label: 'School required', values: rows.map((r) => schoolYears(r.yearsInSchool)) },
                  { label: 'Typical credential', values: rows.map((r) => r.c.credentialLabel ?? 'None') },
                  {
                    label: 'Education debt',
                    info: "Median student debt for the typical credential across related degree fields, weighted by number of schools reporting. Graduate paths add the national median bachelor's debt. When no related field reports debt, it is estimated from the broader field family. Source: College Scorecard.",
                    values: rows.map((r) =>
                      r.c.totalDebt === null
                        ? 'Cost data unavailable'
                        : `${money(r.c.totalDebt)}${r.c.debtEstimated ? ' (estimated)' : ''}`
                    ),
                  },
                  {
                    label: 'Loan interest',
                    info: `Interest paid on the debt over typical ${REPAYMENT_YEARS}-year repayment at ${LOAN_RATE}%.`,
                    values: rows.map((r) => moneyOrNA(r.financials?.interest)),
                  },
                  {
                    label: 'Total cost',
                    info: `Education debt plus loan interest plus ${baseName} earnings given up while in school.`,
                    values: rows.map((r) => moneyOrNA(r.financials?.totalCost)),
                    best: bestIndex(rows.map((r) => r.financials?.totalCost ?? null), false),
                  },
                  {
                    label: 'Payoff timeline',
                    info: `${PAYOFF_EXPLAINER} Compared with ${baseName}.`,
                    values: rows.map((r) =>
                      !r.financials
                        ? 'n/a'
                        : r.financials.totalCost === 0
                          ? 'Nothing to pay off'
                          : r.financials.payoffYears === null
                            ? 'Does not pay off'
                            : years(r.financials.payoffYears)
                    ),
                    best: bestIndex(payoffs, false),
                  },
                  {
                    label: 'Monthly loan payment',
                    info: `Typical ${REPAYMENT_YEARS}-year repayment at ${LOAN_RATE}%.`,
                    values: rows.map((r) => moneyOrNA(r.financials?.monthlyPayment)),
                  },
                ]}
              />
            </CardContent>
          </Card>
        )}

        {rows.length > 0 && (
          <Card>
            <CardContent className="space-y-8 pt-6">
              <BarChartComparison
                title="Salary"
                data={rows.map((r, i) => ({ name: r.c.occupation.name, value: r.salary, color: colorAt(i) }))}
                format={money}
              />
              <BarChartComparison
                title="Total cost"
                data={rows.map((r, i) => ({
                  name: r.c.occupation.name,
                  value: r.financials?.totalCost ?? null,
                  color: colorAt(i),
                }))}
                format={money}
              />
              <BarChartComparison
                title="Payoff timeline (years from starting school)"
                data={rows.map((r, i) => ({
                  name: r.c.occupation.name,
                  value: r.financials && r.financials.totalCost > 0 ? r.financials.payoffYears : null,
                  color: colorAt(i),
                  note: !r.financials
                    ? undefined
                    : r.financials.totalCost === 0
                      ? 'Nothing to pay off'
                      : 'Does not pay off',
                }))}
                format={years}
              />
            </CardContent>
          </Card>
        )}

        <MoreDetails />
      </div>
    </main>
  )
}
