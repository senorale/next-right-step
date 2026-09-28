const DAYS_PER_YEAR = 365;
const MONTHS_PER_YEAR = 12;

// Total interest paid on a student loan using daily simple interest.
// Interest accrues daily on the outstanding principal and is paid in full
// each month, so it never capitalizes (never compounds).
export function calculateTotalInterestPaid(
  loanAmount: number,
  annualInterestRate: number,
  loanDurationYears: number
): number {
  // A 0%, empty (NaN), or otherwise invalid input means no interest is charged.
  if (
    !(annualInterestRate > 0) ||
    !(loanAmount > 0) ||
    !(loanDurationYears > 0)
  ) {
    return 0;
  }

  const dailyRate = annualInterestRate / 100 / DAYS_PER_YEAR;
  const daysPerMonth = DAYS_PER_YEAR / MONTHS_PER_YEAR;
  // Interest accrued per month = principal * dailyRate * days in the month.
  const monthlyRate = dailyRate * daysPerMonth;
  const totalMonths = loanDurationYears * MONTHS_PER_YEAR;

  // Fixed monthly payment that amortizes the loan over its full term.
  const monthlyPayment =
    (loanAmount * monthlyRate * Math.pow(1 + monthlyRate, totalMonths)) /
    (Math.pow(1 + monthlyRate, totalMonths) - 1);

  let remainingBalance = loanAmount;
  let totalInterestPaid = 0;

  for (let month = 0; month < totalMonths; month++) {
    const interestForMonth = remainingBalance * monthlyRate;
    totalInterestPaid += interestForMonth;
    remainingBalance += interestForMonth - monthlyPayment;
  }

  return Math.max(0, totalInterestPaid);
}

export function calculateBreakEvenYears(
  collegeCost: number,
  collegeSalary: number,
  hsSalary: number
): number | string {
  const salaryDifference = collegeSalary - hsSalary;

  if (salaryDifference <= 0) {
    return "College salary does not exceed high school salary, break-even not possible.";
  }

  const breakEvenYears = collegeCost / salaryDifference;
  return breakEvenYears;
}

/**
 * Years until an education investment is recovered by the salary gain over a
 * baseline (HS diploma, current salary, etc.). Returns null when the new
 * salary does not exceed the baseline, meaning it never pays off.
 */
export function calculatePayoffYears(
  totalCost: number,
  newSalary: number,
  baselineSalary: number
): number | null {
  const salaryDelta = newSalary - baselineSalary;
  if (salaryDelta <= 0) return null;
  return totalCost / salaryDelta;
}

  