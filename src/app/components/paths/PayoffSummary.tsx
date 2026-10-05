import { InfoTooltip } from '../calculator/InfoTooltip'
import type { Financials } from './finance'
import { LOAN_RATE, PAYOFF_EXPLAINER, REPAYMENT_YEARS } from './finance'
import { money, years } from './format'

function Stat({ label, value, info }: { label: string; value: string; info?: string }) {
  return (
    <div className="rounded-lg border p-3">
      <div className="text-xs text-muted-foreground">
        {label}
        {info && <InfoTooltip content={info} />}
      </div>
      <div className="text-lg font-semibold tabular-nums">{value}</div>
    </div>
  )
}

/** Debt, monthly payment, total cost, and payoff timeline for one option. */
export default function PayoffSummary({
  financials,
  payoffLabel = 'Payoff timeline',
  baselineLabel,
}: {
  financials: Financials
  payoffLabel?: string
  baselineLabel: string
}) {
  const f = financials
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <Stat label="Education debt" value={money(f.debt)} />
      <Stat
        label="Monthly payment"
        value={money(f.monthlyPayment)}
        info={`Typical ${REPAYMENT_YEARS}-year repayment (what most borrowers take, not the 10-year standard plan) at ${LOAN_RATE}% federal rate.`}
      />
      <Stat
        label="Total cost"
        value={money(f.totalCost)}
        info={`Debt plus ${money(f.interest)} loan interest plus ${money(f.opportunityCost)} of ${baselineLabel} earnings given up while in school.`}
      />
      <Stat
        label={payoffLabel}
        value={f.payoffYears === null ? 'Does not pay off' : years(f.payoffYears)}
        info={`${PAYOFF_EXPLAINER} Compared with ${baselineLabel}.`}
      />
    </div>
  )
}
