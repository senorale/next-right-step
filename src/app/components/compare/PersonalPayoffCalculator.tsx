'use client'

import { useMemo } from 'react'
import { calculateTotalInterestPaid, calculateBreakEvenYears } from '../../utils'
import * as CollegeConstants from '@/app/constants/college_related_constants'
import { InfoTooltip } from '../calculator/InfoTooltip'
import { Slider } from '@/components/ui/slider'

const HS_SALARY = CollegeConstants.HIGHSCHOOL_DIPLOMA_MEDIAN_SALARY
const DEFAULT_RATE = parseFloat(CollegeConstants.STUDENT_LOAN_INTEREST_RATE)

const fmt = (n: number) => `$${Math.round(n).toLocaleString()}`

export interface PersonalParams {
  debt: number
  salary: number
  interestRate: number
  termYears: number
  yearsInSchool: number
}

export default function PersonalPayoffCalculator({
  params,
  onParamsChange,
  degreeName,
}: {
  params: PersonalParams
  onParamsChange: (params: PersonalParams) => void
  degreeName: string
}) {
  const update = (patch: Partial<PersonalParams>) =>
    onParamsChange({ ...params, ...patch })

  const totals = useMemo(() => {
    const interest = calculateTotalInterestPaid(params.debt, params.interestRate, params.termYears)
    const opportunity = HS_SALARY * params.yearsInSchool
    const totalRepaid = params.debt + interest
    const totalCost = totalRepaid + opportunity
    const breakEven = calculateBreakEvenYears(totalCost, params.salary, HS_SALARY)
    const monthlyRate = params.interestRate / 100 / 12
    const n = params.termYears * 12
    let monthly = 0
    if (params.debt > 0) {
      monthly = params.interestRate > 0
        ? (params.debt * monthlyRate * Math.pow(1 + monthlyRate, n)) / (Math.pow(1 + monthlyRate, n) - 1)
        : params.debt / (params.termYears * 12)
    }
    return { interest, opportunity, totalRepaid, totalCost, breakEven, monthly }
  }, [params])

  return (
    <div className="space-y-6">
      <div className="space-y-4">
        <SliderField
          label="Total student debt"
          tooltip="Total amount you expect to borrow, including all years."
          value={params.debt}
          display={fmt(params.debt)}
          min={0}
          max={500000}
          step={1000}
          onChange={(v) => update({ debt: v })}
        />

        <SliderField
          label="Expected salary"
          tooltip={`Your expected annual salary after graduating. Adjust to match your expectations for ${degreeName}.`}
          value={params.salary}
          display={`${fmt(params.salary)}/yr`}
          min={20000}
          max={350000}
          step={1000}
          onChange={(v) => update({ salary: v })}
        />

        <SliderField
          label="Years in school"
          value={params.yearsInSchool}
          display={`${params.yearsInSchool} years`}
          min={1}
          max={14}
          step={1}
          onChange={(v) => update({ yearsInSchool: v })}
        />

        <SliderField
          label="Interest rate"
          value={params.interestRate}
          display={`${params.interestRate.toFixed(1)}%`}
          min={0}
          max={15}
          step={0.5}
          onChange={(v) => update({ interestRate: v })}
        />

        <SliderField
          label="Repayment term"
          tooltip="Longer terms lower monthly payments but increase total interest."
          value={params.termYears}
          display={`${params.termYears} years`}
          min={5}
          max={30}
          step={1}
          onChange={(v) => update({ termYears: v })}
        />
      </div>

      <div className="grid grid-cols-2 gap-4 text-center">
        <Stat label="Monthly payment" value={fmt(totals.monthly)} />
        <Stat label="Total interest" value={fmt(totals.interest)} />
        <Stat label="Total repaid" value={fmt(totals.totalRepaid)} />
        <Stat label={`Opportunity cost (${params.yearsInSchool}yr)`} value={fmt(totals.opportunity)} />
      </div>

      <div className="border-t pt-4 text-center">
        <div className="text-sm text-muted-foreground">Total cost</div>
        <div className="text-2xl font-bold">{fmt(totals.totalCost)}</div>
      </div>

      <div className="text-center">
        <div className="flex items-center justify-center gap-1 text-sm text-muted-foreground">
          Break-even point
          <InfoTooltip content="Years after graduation for higher salary to offset total cost, compared to a high-school diploma." />
        </div>
        <div className="text-xl font-bold">
          {typeof totals.breakEven === 'number'
            ? `${Math.round(totals.breakEven * 10) / 10} years`
            : 'N/A'}
        </div>
      </div>

      <p className="text-xs text-muted-foreground text-center">
        Opportunity cost: {fmt(HS_SALARY)}/yr foregone earnings while in school.
        Default interest rate: {DEFAULT_RATE}% (federal undergraduate, 2026-2027).
      </p>
    </div>
  )
}

function SliderField({
  label,
  tooltip,
  value,
  display,
  min,
  max,
  step,
  onChange,
}: {
  label: string
  tooltip?: string
  value: number
  display: string
  min: number
  max: number
  step: number
  onChange: (v: number) => void
}) {
  return (
    <div>
      <div className="flex items-center justify-between text-sm font-medium mb-2">
        <span className="flex items-center gap-1">
          {label}
          {tooltip && <InfoTooltip content={tooltip} />}
        </span>
        <span className="tabular-nums">{display}</span>
      </div>
      <Slider
        value={[value]}
        min={min}
        max={max}
        step={step}
        onValueChange={(v) => onChange(v[0])}
      />
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
