import { calculateMonthlyPayment, calculatePayoffYears } from '@/app/utils'
import * as C from '@/app/constants/college_related_constants'

export const HS_SALARY = C.HIGHSCHOOL_DIPLOMA_MEDIAN_SALARY
export const LOAN_RATE = parseFloat(C.STUDENT_LOAN_INTEREST_RATE)
export const REPAYMENT_YEARS = C.STANDARD_REPAYMENT_YEARS

export interface Financials {
  debt: number
  opportunityCost: number
  totalCost: number
  monthlyPayment: number
  salaryDelta: number
  /** null when the salary never exceeds the baseline */
  payoffYears: number | null
}

/**
 * Total cost = education debt + salary given up while in school.
 * Payoff timeline = total cost / (salary - baseline salary).
 */
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
  const opportunityCost = baselineSalary * yearsInSchool
  const totalCost = debt + opportunityCost
  return {
    debt,
    opportunityCost,
    totalCost,
    monthlyPayment: calculateMonthlyPayment(debt, LOAN_RATE, REPAYMENT_YEARS),
    salaryDelta: salary - baselineSalary,
    payoffYears: totalCost === 0 ? 0 : calculatePayoffYears(totalCost, salary, baselineSalary),
  }
}
