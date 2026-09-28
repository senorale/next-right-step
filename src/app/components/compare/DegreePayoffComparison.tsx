'use client'

import { useMemo } from 'react'
import { calculateTotalInterestPaid, calculateBreakEvenYears } from '../../utils'
import * as CollegeConstants from '@/app/constants/college_related_constants'
import { InfoTooltip } from '../calculator/InfoTooltip'
import { Slider } from '@/components/ui/slider'

const HS_SALARY = CollegeConstants.HIGHSCHOOL_DIPLOMA_MEDIAN_SALARY

const fmt = (n: number) => `$${Math.round(n).toLocaleString()}`

function monthlyPayment(principal: number, annualRate: number, years: number): number {
  if (principal <= 0 || years <= 0) return 0
  if (annualRate <= 0) return principal / (years * 12)
  const monthlyRate = annualRate / 100 / 12
  const n = years * 12
  return (principal * monthlyRate * Math.pow(1 + monthlyRate, n)) / (Math.pow(1 + monthlyRate, n) - 1)
}

function SchoolColumn({
  label,
  annualTuition,
  onTuitionChange,
  salary,
  interestRate,
  termYears,
  schoolYears,
}: {
  label: string
  annualTuition: number
  onTuitionChange: (v: number) => void
  salary: number
  interestRate: number
  termYears: number
  schoolYears: number
}) {
  const totals = useMemo(() => {
    const tuition = annualTuition * schoolYears
    const interest = calculateTotalInterestPaid(tuition, interestRate, termYears)
    const opportunity = HS_SALARY * schoolYears
    const total = tuition + interest + opportunity
    const breakEven = calculateBreakEvenYears(total, salary, HS_SALARY)
    const monthly = monthlyPayment(tuition, interestRate, termYears)
    return { tuition, interest, opportunity, total, breakEven, monthly }
  }, [annualTuition, salary, interestRate, termYears, schoolYears])

  return (
    <div className="flex-1 space-y-4">
      <h3 className="text-sm font-semibold text-center">{label}</h3>

      <div>
        <div className="flex items-center justify-between text-sm font-medium mb-2">
          <span>Annual tuition</span>
          <span className="tabular-nums">{fmt(annualTuition)}</span>
        </div>
        <Slider
          value={[annualTuition]}
          min={0}
          max={80000}
          step={500}
          onValueChange={(v) => onTuitionChange(v[0])}
        />
      </div>

      <div className="space-y-2 text-center">
        <Stat label={`Tuition (${schoolYears} yr)`} value={fmt(totals.tuition)} />
        <Stat label="Monthly payment" value={fmt(totals.monthly)} />
        <Stat label="Total interest" value={fmt(totals.interest)} />
        <Stat label="Opportunity cost" value={fmt(totals.opportunity)} />
      </div>
      <div className="border-t pt-3 text-center">
        <div className="text-sm text-muted-foreground">Total cost</div>
        <div className="text-xl font-bold">{fmt(totals.total)}</div>
      </div>
      <div className="text-center">
        <div className="flex items-center justify-center gap-1 text-sm text-muted-foreground">
          Pay-off point
          <InfoTooltip content="Years for the higher salary to offset the total cost, versus a high-school diploma." />
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

export interface ComparisonData {
  major: { id: string; name: string }
  weightedSalary: number
  weightedYears: number
  tuition: {
    publicInState: number
    privateNonprofit: number
  }
}

export interface ComparisonParams {
  salary: number
  publicTuition: number
  privateTuition: number
  interestRate: number
  termYears: number
}

export default function DegreePayoffComparison({
  data,
  params,
  onParamsChange,
}: {
  data: ComparisonData
  params: ComparisonParams
  onParamsChange: (params: ComparisonParams) => void
}) {
  const update = (patch: Partial<ComparisonParams>) =>
    onParamsChange({ ...params, ...patch })

  return (
    <div className="space-y-6">
      <div className="space-y-4">
        <div>
          <div className="flex items-center justify-between text-sm font-medium mb-2">
            <span className="flex items-center gap-1">
              Expected salary
              <InfoTooltip content={`Defaults to the weighted average salary for ${data.major.name} graduates. Adjust to match your expectations.`} />
            </span>
            <span className="tabular-nums">{fmt(params.salary)}/yr</span>
          </div>
          <Slider
            value={[params.salary]}
            min={20000}
            max={250000}
            step={1000}
            onValueChange={(v) => update({ salary: v[0] })}
          />
        </div>

        <div>
          <div className="flex items-center justify-between text-sm font-medium mb-2">
            <span>Interest rate</span>
            <span className="tabular-nums">{params.interestRate.toFixed(1)}%</span>
          </div>
          <Slider
            value={[params.interestRate]}
            min={0}
            max={15}
            step={0.5}
            onValueChange={(v) => update({ interestRate: v[0] })}
          />
        </div>

        <div>
          <div className="flex items-center justify-between text-sm font-medium mb-2">
            <span className="flex items-center gap-1">
              Repayment term
              <InfoTooltip content="Longer terms lower monthly payments but cost more in total interest." />
            </span>
            <span className="tabular-nums">{params.termYears} years</span>
          </div>
          <Slider
            value={[params.termYears]}
            min={10}
            max={30}
            step={1}
            onValueChange={(v) => update({ termYears: v[0] })}
          />
        </div>
      </div>

      <div className="flex gap-4">
        <SchoolColumn
          label="Public In-State"
          annualTuition={params.publicTuition}
          onTuitionChange={(v) => update({ publicTuition: v })}
          salary={params.salary}
          interestRate={params.interestRate}
          termYears={params.termYears}
          schoolYears={data.weightedYears}
        />
        <div className="w-px bg-border" />
        <SchoolColumn
          label="Private Nonprofit"
          annualTuition={params.privateTuition}
          onTuitionChange={(v) => update({ privateTuition: v })}
          salary={params.salary}
          interestRate={params.interestRate}
          termYears={params.termYears}
          schoolYears={data.weightedYears}
        />
      </div>

      <p className="text-xs text-muted-foreground text-center">
        Tuition: College Scorecard median net price. Salary: BLS May 2024.
        Opportunity cost: {fmt(HS_SALARY)}/yr foregone earnings over {data.weightedYears} years.
      </p>
    </div>
  )
}
