import { calculateMonthlyPayment, calculatePayoffYears, calculateTotalInterestPaid } from '@/app/utils'
import * as C from '@/app/constants/college_related_constants'

export const HS_SALARY = C.HIGHSCHOOL_DIPLOMA_MEDIAN_SALARY
export const LOAN_RATE = parseFloat(C.STUDENT_LOAN_INTEREST_RATE)
export const REPAYMENT_YEARS = C.TYPICAL_REPAYMENT_YEARS

/** How every payoff timeline in the app is counted; shown wherever one appears. */
export const PAYOFF_EXPLAINER =
  'Years from the first day of school until the higher pay recovers the total cost. Assumes full-time school ' +
  'with no income in the meantime, and median pay right after graduating. Starting pay is often lower than ' +
  'the median, so the real payoff usually takes longer.'

export interface Financials {
  debt: number
  /** Interest paid over typical repayment of the debt */
  interest: number
  opportunityCost: number
  totalCost: number
  monthlyPayment: number
  salaryDelta: number
  /** Years from the first day of school; null when the salary never exceeds the baseline */
  payoffYears: number | null
}

/**
 * Total cost = education debt + loan interest + salary given up while in school
 * (full-time school, no income meanwhile).
 * Payoff timeline = years in school + total cost / (salary - baseline salary),
 * counted from the first day of school.
 */
function withSchoolYears(yearsAfterSchool: number | null, yearsInSchool: number): number | null {
  return yearsAfterSchool === null ? null : yearsInSchool + yearsAfterSchool
}

export function computeFinancials({
  debt,
  yearsInSchool,
  salary,
  baselineSalary,
}: {
  debt: number
  yearsInSchool: number
  salary: number
  baselineSalary: number
}): Financials {
  const interest = calculateTotalInterestPaid(debt, LOAN_RATE, REPAYMENT_YEARS)
  const opportunityCost = baselineSalary * yearsInSchool
  const totalCost = debt + interest + opportunityCost
  return {
    debt,
    interest,
    opportunityCost,
    totalCost,
    monthlyPayment: calculateMonthlyPayment(debt, LOAN_RATE, REPAYMENT_YEARS),
    salaryDelta: salary - baselineSalary,
    payoffYears: totalCost === 0 ? 0 : withSchoolYears(calculatePayoffYears(totalCost, salary, baselineSalary), yearsInSchool),
  }
}
