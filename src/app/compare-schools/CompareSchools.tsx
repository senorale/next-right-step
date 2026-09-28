'use client'

import { useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import * as C from '@/app/constants/college_related_constants'
import PathHeader from '../components/paths/PathHeader'
import SchoolSearch from '../components/paths/SchoolSearch'
import SelectedPills from '../components/paths/SelectedPills'
import ComparisonTable, { bestIndex, type ComparisonRow } from '../components/paths/ComparisonTable'
import BarChartComparison from '../components/paths/BarChartComparison'
import { HS_SALARY, LOAN_RATE, REPAYMENT_YEARS } from '../components/paths/finance'
import { calculateMonthlyPayment, calculatePayoffYears } from '@/app/utils'
import { colorAt, money, moneyOrNA, pctOrNA, ratio, years } from '../components/paths/format'
import type { School } from '../components/paths/types'

const MAX_SCHOOLS = 5
const YEARS_IN_SCHOOL = parseFloat(C.BACHELOR_YEARS_IN_SCHOOL)

const INCOME_BRACKETS: { key: string; label: string }[] = [
  { key: 'overall', label: 'Average' },
  { key: '0-30000', label: 'Under $30k' },
  { key: '30001-48000', label: '$30k-48k' },
  { key: '48001-75000', label: '$48k-75k' },
  { key: '75001-110000', label: '$75k-110k' },
  { key: '110001-plus', label: '$110k+' },
]

type MetricKey = 'net_price' | 'graduation' | 'debt' | 'earnings' | 'admission' | 'retention' | 'repayment'

const METRICS: { key: MetricKey; label: string }[] = [
  { key: 'net_price', label: 'Net price' },
  { key: 'graduation', label: 'Graduation rate' },
  { key: 'debt', label: 'Median debt' },
  { key: 'earnings', label: 'Earnings' },
  { key: 'admission', label: 'Admission rate' },
  { key: 'retention', label: 'Retention rate' },
  { key: 'repayment', label: 'Loan repayment' },
]

function netPrice(s: School, bracket: string): number | null {
  if (bracket === 'overall') return s.avg_net_price
  return s.net_price_by_income?.[bracket] ?? null
}

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      aria-pressed={active}
      onClick={onClick}
      className={`rounded-full border px-3 py-1 text-sm transition-colors ${
        active ? 'border-primary bg-primary text-primary-foreground' : 'hover:bg-accent'
      }`}
    >
      {children}
    </button>
  )
}

export default function CompareSchools() {
  const [schools, setSchools] = useState<School[]>([])
  const [bracket, setBracket] = useState('overall')
  const [metrics, setMetrics] = useState<Set<MetricKey>>(new Set(METRICS.map((m) => m.key)))

  const toggleMetric = (k: MetricKey) =>
    setMetrics((prev) => {
      const next = new Set(prev)
      if (next.has(k)) next.delete(k)
      else next.add(k)
      return next
    })

  const rows = schools.map((s) => {
    const price = netPrice(s, bracket)
    const totalCost = price == null ? null : price * YEARS_IN_SCHOOL
    return {
      s,
      price,
      totalCost,
      payoffYears:
        totalCost == null || s.earnings_10yr == null ? null : calculatePayoffYears(totalCost, s.earnings_10yr, HS_SALARY),
      earningsToDebt: s.earnings_10yr != null && s.median_debt ? s.earnings_10yr / s.median_debt : null,
      monthly: s.median_debt == null ? null : calculateMonthlyPayment(s.median_debt, LOAN_RATE, REPAYMENT_YEARS),
    }
  })
  const bracketLabel = INCOME_BRACKETS.find((b) => b.key === bracket)?.label ?? ''

  const metricRows: Record<MetricKey, ComparisonRow> = {
    net_price: {
      label: `Net price per year (${bracketLabel})`,
      info: 'Cost of attendance minus grants and scholarships, for the selected family income. Source: College Scorecard.',
      values: rows.map((r) => moneyOrNA(r.price)),
      best: bestIndex(rows.map((r) => r.price), false),
    },
    graduation: {
      label: 'Graduation rate',
      values: rows.map((r) => pctOrNA(r.s.graduation_rate)),
      best: bestIndex(rows.map((r) => r.s.graduation_rate), true),
    },
    debt: {
      label: 'Median debt at graduation',
      values: rows.map((r) => moneyOrNA(r.s.median_debt)),
      best: bestIndex(rows.map((r) => r.s.median_debt), false),
    },
    earnings: {
      label: 'Earnings 10 yrs after entry',
      info: 'Median earnings of students 10 years after they started, including those who did not graduate.',
      values: rows.map((r) => moneyOrNA(r.s.earnings_10yr)),
      best: bestIndex(rows.map((r) => r.s.earnings_10yr), true),
    },
    admission: {
      label: 'Admission rate',
      values: rows.map((r) => pctOrNA(r.s.admission_rate)),
    },
    retention: {
      label: 'Retention rate',
      info: 'Share of first-year full-time students who return for a second year.',
      values: rows.map((r) => pctOrNA(r.s.retention_rate)),
      best: bestIndex(rows.map((r) => r.s.retention_rate), true),
    },
    repayment: {
      label: 'Loan repayment rate (3 yrs)',
      info: 'Share of borrowers who paid down at least $1 of principal within 3 years.',
      values: rows.map((r) => pctOrNA(r.s.repayment_rate_3yr)),
      best: bestIndex(rows.map((r) => r.s.repayment_rate_3yr), true),
    },
  }

  const atMax = schools.length >= MAX_SCHOOLS

  return (
    <main className="flex min-h-screen flex-col items-center p-4 sm:p-6 md:p-16">
      <div className="w-full max-w-3xl space-y-6">
        <PathHeader
          title="Compare schools"
          description="Put colleges side by side on cost, outcomes, and how fast the degree pays for itself."
        />

        <Card>
          <CardHeader>
            <CardTitle className="text-lg">
              Schools{' '}
              <span className="text-sm font-normal text-muted-foreground">
                ({schools.length}/{MAX_SCHOOLS})
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <SchoolSearch
              onSelect={(s) => setSchools((prev) => (prev.length < MAX_SCHOOLS ? [...prev, s] : prev))}
              excludeIds={schools.map((s) => s.school_id)}
              disabled={atMax}
              placeholder={atMax ? 'Remove one to add another' : 'Search schools by name…'}
            />
            {schools.length > 0 ? (
              <SelectedPills
                items={schools.map((s) => ({ key: String(s.school_id), label: s.name }))}
                onRemove={(id) => setSchools((prev) => prev.filter((s) => String(s.school_id) !== id))}
              />
            ) : (
              <p className="text-sm text-muted-foreground">Add up to {MAX_SCHOOLS} schools.</p>
            )}
          </CardContent>
        </Card>

        {rows.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">What to compare</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-wrap gap-2">
                {METRICS.map((m) => (
                  <Chip key={m.key} active={metrics.has(m.key)} onClick={() => toggleMetric(m.key)}>
                    {m.label}
                  </Chip>
                ))}
              </div>
              <div className="space-y-2">
                <p className="text-sm font-medium">Family income (sets net price)</p>
                <div className="flex flex-wrap gap-2">
                  {INCOME_BRACKETS.map((b) => (
                    <Chip key={b.key} active={bracket === b.key} onClick={() => setBracket(b.key)}>
                      {b.label}
                    </Chip>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {rows.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Side by side</CardTitle>
            </CardHeader>
            <CardContent>
              <ComparisonTable
                columns={rows.map((r, i) => ({ key: String(r.s.school_id), label: r.s.name, color: colorAt(i) }))}
                rows={[
                  ...METRICS.filter((m) => metrics.has(m.key)).map((m) => metricRows[m.key]),
                  {
                    label: 'Payoff timeline',
                    info: `Net price x ${YEARS_IN_SCHOOL} years, divided by the yearly earnings gain over a high school diploma (${money(HS_SALARY)}).`,
                    values: rows.map((r) =>
                      r.totalCost == null || r.s.earnings_10yr == null
                        ? 'n/a'
                        : r.payoffYears === null
                          ? 'Does not pay off'
                          : years(r.payoffYears)
                    ),
                    best: bestIndex(rows.map((r) => r.payoffYears), false),
                  },
                  {
                    label: 'Earnings-to-debt ratio',
                    info: 'Earnings 10 yrs after entry per dollar of median debt. Higher is better.',
                    values: rows.map((r) => ratio(r.earningsToDebt)),
                    best: bestIndex(rows.map((r) => r.earningsToDebt), true),
                  },
                  {
                    label: 'Monthly payment on median debt',
                    info: `Standard ${REPAYMENT_YEARS}-year repayment at ${LOAN_RATE}%.`,
                    values: rows.map((r) => moneyOrNA(r.monthly)),
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
                title={`Net price per year (${bracketLabel})`}
                data={rows.map((r, i) => ({ name: r.s.name, value: r.price, color: colorAt(i) }))}
                format={money}
              />
              <BarChartComparison
                title="Earnings 10 yrs after entry"
                data={rows.map((r, i) => ({ name: r.s.name, value: r.s.earnings_10yr, color: colorAt(i) }))}
                format={money}
              />
              <BarChartComparison
                title="Payoff timeline (years)"
                data={rows.map((r, i) => ({ name: r.s.name, value: r.payoffYears, color: colorAt(i) }))}
                format={years}
              />
            </CardContent>
          </Card>
        )}

        <p className="text-center text-sm text-muted-foreground">
          School data: College Scorecard (U.S. Department of Education). Not inflation-adjusted.
        </p>
      </div>
    </main>
  )
}
