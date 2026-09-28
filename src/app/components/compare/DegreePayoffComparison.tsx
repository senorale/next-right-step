'use client'

import { useMemo } from 'react'
import { calculateTotalInterestPaid, calculateBreakEvenYears } from '../../utils'
import * as CollegeConstants from '@/app/constants/college_related_constants'
import { InfoTooltip } from '../calculator/InfoTooltip'

const HS_SALARY = CollegeConstants.HIGHSCHOOL_DIPLOMA_MEDIAN_SALARY
const DEFAULT_RATE = parseFloat(CollegeConstants.STUDENT_LOAN_INTEREST_RATE)
const DEFAULT_TERM = 20

const fmt = (n: number) => `$${Math.round(n).toLocaleString()}`

export interface DebtData {
  credentialLevel: number
  credentialLabel: string
  public: number | null
  privateNonprofit: number | null
  all: number | null
  sampleSize: number
}

export interface ComparisonData {
  degree: { id: string; name: string }
  weightedSalary: number
  weightedYears: number
  debt: DebtData | null
}

function DebtColumn({
  label,
  medianDebt,
  salary,
  schoolYears,
}: {
  label: string
  medianDebt: number
  salary: number
  schoolYears: number
}) {
  const totals = useMemo(() => {
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
    return { interest, opportunity, totalRepaid, totalCost, breakEven, monthly }
  }, [medianDebt, salary, schoolYears])

  return (
    <div className="flex-1 space-y-4">
      <h3 className="text-sm font-semibold text-center">{label}</h3>

      <div className="space-y-2 text-center">
        <Stat label="Median debt at graduation" value={fmt(medianDebt)} />
        <Stat label="Monthly payment" value={fmt(totals.monthly)} />
        <Stat label={`Total interest (${DEFAULT_RATE}%, ${DEFAULT_TERM}yr)`} value={fmt(totals.interest)} />
        <Stat label="Total repaid" value={fmt(totals.totalRepaid)} />
        <Stat label={`Opportunity cost (${schoolYears}yr)`} value={fmt(totals.opportunity)} />
      </div>
      <div className="border-t pt-3 text-center">
        <div className="text-sm text-muted-foreground">Total cost</div>
        <div className="text-xl font-bold">{fmt(totals.totalCost)}</div>
      </div>
      <div className="text-center">
        <div className="flex items-center justify-center gap-1 text-sm text-muted-foreground">
          Break-even point
          <InfoTooltip content="Years after graduation for higher salary to offset total cost, compared to a high-school diploma." />
        </div>
        <div className="text-lg font-bold">
          {typeof totals.breakEven === 'number'
            ? `${Math.round(totals.breakEven * 10) / 10} years`
            : 'N/A'}
        </div>
      </div>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-base font-semibold">{value}</div>
    </div>
  )
}

export default function DegreePayoffComparison({
  data,
}: {
  data: ComparisonData
}) {
  if (!data.debt) {
    return (
      <p className="text-sm text-muted-foreground text-center py-4">
        No debt data available for {data.degree.name}. College Scorecard does not report
        debt data for all degrees.
      </p>
    )
  }

  const hasPublic = data.debt.public != null
  const hasPrivate = data.debt.privateNonprofit != null
  const hasBoth = hasPublic && hasPrivate

  return (
    <div className="space-y-6">
      <div className="text-center space-y-1">
        <div className="text-sm font-medium">{data.degree.name}</div>
        <div className="text-xs text-muted-foreground">
          {data.debt.credentialLabel} · {data.weightedYears} years · {fmt(data.weightedSalary)}/yr median salary
        </div>
      </div>

      <div className={`flex ${hasBoth ? 'gap-4' : 'justify-center'}`}>
        {hasPublic && (
          <DebtColumn
            label="Public"
            medianDebt={data.debt.public!}
            salary={data.weightedSalary}
            schoolYears={data.weightedYears}
          />
        )}
        {hasBoth && <div className="w-px bg-border" />}
        {hasPrivate && (
          <DebtColumn
            label="Private Nonprofit"
            medianDebt={data.debt.privateNonprofit!}
            salary={data.weightedSalary}
            schoolYears={data.weightedYears}
          />
        )}
        {!hasPublic && !hasPrivate && data.debt.all != null && (
          <DebtColumn
            label="All Schools"
            medianDebt={data.debt.all}
            salary={data.weightedSalary}
            schoolYears={data.weightedYears}
          />
        )}
      </div>

      <p className="text-xs text-muted-foreground text-center">
        Debt: College Scorecard median across {data.debt.sampleSize} schools.
        Salary: BLS May 2024. Interest: {DEFAULT_RATE}% over {DEFAULT_TERM} years.
        Opportunity cost: {fmt(HS_SALARY)}/yr foregone earnings.
      </p>
    </div>
  )
}
