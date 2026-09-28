'use client'

import { useMemo } from 'react'
import { X } from 'lucide-react'
import { calculateTotalInterestPaid, calculateBreakEvenYears } from '../../utils'
import * as CollegeConstants from '@/app/constants/college_related_constants'
import { InfoTooltip } from '../calculator/InfoTooltip'
import type { ComparisonData } from './DegreePayoffComparison'

const HS_SALARY = CollegeConstants.HIGHSCHOOL_DIPLOMA_MEDIAN_SALARY
const DEFAULT_RATE = parseFloat(CollegeConstants.STUDENT_LOAN_INTEREST_RATE)
const DEFAULT_TERM = 20

const fmt = (n: number) => `$${Math.round(n).toLocaleString()}`

const COLORS = [
  'hsl(var(--chart-1))',
  'hsl(var(--chart-2))',
  'hsl(var(--chart-3))',
]

function computeTotals(medianDebt: number, salary: number, schoolYears: number) {
  const interest = calculateTotalInterestPaid(medianDebt, DEFAULT_RATE, DEFAULT_TERM)
  const opportunity = HS_SALARY * schoolYears
  const totalRepaid = medianDebt + interest
  const totalCost = totalRepaid + opportunity
  const breakEven = calculateBreakEvenYears(totalCost, salary, HS_SALARY)
  const monthlyRate = DEFAULT_RATE / 100 / 12
  const n = DEFAULT_TERM * 12
  const monthly = medianDebt > 0 && DEFAULT_RATE > 0
    ? (medianDebt * monthlyRate * Math.pow(1 + monthlyRate, n)) / (Math.pow(1 + monthlyRate, n) - 1)
    : medianDebt / (DEFAULT_TERM * 12)
  return { interest, opportunity, totalRepaid, totalCost, breakEven, monthly, medianDebt }
}

export default function CompareDegreesTab({
  degrees,
  onRemove,
}: {
  degrees: ComparisonData[]
  onRemove: (id: string) => void
}) {
  const rows = useMemo(() => {
    return degrees.map((m) => {
      const debt = m.debt?.all ?? m.debt?.public ?? m.debt?.privateNonprofit ?? 0
      return {
        ...m,
        totals: computeTotals(debt, m.weightedSalary, m.weightedYears),
      }
    })
  }, [degrees])

  if (rows.length === 0) {
    return (
      <p className="text-sm text-muted-foreground text-center py-8">
        Search and add up to 3 degrees to compare debt, salary, and break-even.
      </p>
    )
  }

  const maxDebt = Math.max(1, ...rows.map((r) => r.totals.medianDebt))
  const maxCost = Math.max(1, ...rows.map((r) => r.totals.totalCost))

  return (
    <div className="space-y-6">
      {/* Pills */}
      <div className="flex flex-wrap gap-2">
        {rows.map((r, i) => (
          <span
            key={r.degree.id}
            className="inline-flex items-center gap-1 rounded-full border px-3 py-1 text-sm"
            style={{ borderColor: COLORS[i % COLORS.length] }}
          >
            {r.degree.name}
            <button
              onClick={() => onRemove(r.degree.id)}
              aria-label={`Remove ${r.degree.name}`}
              className="text-muted-foreground hover:text-foreground"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </span>
        ))}
      </div>

      {/* Comparison table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b">
              <th className="text-left py-2 pr-4 font-medium text-muted-foreground" />
              {rows.map((r, i) => (
                <th
                  key={r.degree.id}
                  className="text-center py-2 px-2 font-semibold"
                  style={{ color: COLORS[i % COLORS.length] }}
                >
                  {r.degree.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <Row label="Education level" values={rows.map((r) => r.debt?.credentialLabel ?? 'N/A')} />
            <Row label="Years in school" values={rows.map((r) => String(r.weightedYears))} />
            <Row label="Median salary" values={rows.map((r) => fmt(r.weightedSalary))} />
            <Row label="Median debt" values={rows.map((r) => fmt(r.totals.medianDebt))} />
            <Row label="Monthly payment" values={rows.map((r) => fmt(r.totals.monthly))} />
            <Row label="Total interest" values={rows.map((r) => fmt(r.totals.interest))} />
            <Row label="Opportunity cost" values={rows.map((r) => fmt(r.totals.opportunity))} />
            <Row label="Total cost" values={rows.map((r) => fmt(r.totals.totalCost))} bold />
            <Row
              label={
                <span className="flex items-center gap-1">
                  Break-even
                  <InfoTooltip content="Years after graduation for higher salary to offset total cost, compared to a high-school diploma." />
                </span>
              }
              values={rows.map((r) =>
                typeof r.totals.breakEven === 'number'
                  ? `${Math.round(r.totals.breakEven * 10) / 10} years`
                  : 'N/A'
              )}
              bold
            />
          </tbody>
        </table>
      </div>

      {/* Debt bar chart */}
      <div className="space-y-3">
        <div className="text-xs font-medium text-muted-foreground">Median debt</div>
        {rows.map((r, i) => (
          <div key={r.degree.id} className="space-y-1">
            <div className="flex items-center justify-between text-xs">
              <span className="truncate pr-2">{r.degree.name}</span>
              <span className="shrink-0 tabular-nums font-semibold">{fmt(r.totals.medianDebt)}</span>
            </div>
            <div className="h-3 w-full overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full transition-all"
                style={{
                  width: `${(r.totals.medianDebt / maxDebt) * 100}%`,
                  backgroundColor: COLORS[i % COLORS.length],
                }}
              />
            </div>
          </div>
        ))}
      </div>

      {/* Total cost bar chart */}
      <div className="space-y-3">
        <div className="text-xs font-medium text-muted-foreground">Total cost</div>
        {rows.map((r, i) => (
          <div key={r.degree.id} className="space-y-1">
            <div className="flex items-center justify-between text-xs">
              <span className="truncate pr-2">{r.degree.name}</span>
              <span className="shrink-0 tabular-nums font-semibold">{fmt(r.totals.totalCost)}</span>
            </div>
            <div className="h-3 w-full overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full transition-all"
                style={{
                  width: `${(r.totals.totalCost / maxCost) * 100}%`,
                  backgroundColor: COLORS[i % COLORS.length],
                }}
              />
            </div>
          </div>
        ))}
      </div>

      <p className="text-xs text-muted-foreground text-center">
        Debt: College Scorecard median (all school types). Salary: BLS May 2024.
        Interest: {DEFAULT_RATE}% over {DEFAULT_TERM} years.
        Opportunity cost: {fmt(HS_SALARY)}/yr foregone earnings.
      </p>
    </div>
  )
}

function Row({
  label,
  values,
  bold,
}: {
  label: React.ReactNode
  values: string[]
  bold?: boolean
}) {
  return (
    <tr className="border-b last:border-0">
      <td className="py-2 pr-4 text-muted-foreground whitespace-nowrap">{label}</td>
      {values.map((v, i) => (
        <td
          key={i}
          className={`py-2 px-2 text-center tabular-nums ${bold ? 'font-bold' : ''}`}
        >
          {v}
        </td>
      ))}
    </tr>
  )
}
