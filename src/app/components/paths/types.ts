// Client-side shapes of the path page API responses.

export interface Occupation {
  id: string
  name: string
  annual_salary: number
  typical_years_of_school: number | null
}

export interface Degree {
  id: string
  code: string
  name: string
  occupationIds: string[]
}

/** GET /api/career-cost */
export interface CareerCost {
  occupation: Occupation & { occupation_code: string }
  credentialLevels: number[]
  credentialLabel: string | null
  medianDebt: number | null
  debtSampleSize: number
  undergradDebt: number
  totalDebt: number | null
  degrees: { code: string; title: string }[]
}

/** Row of the School table as returned by /api/schools/* */
export interface School {
  school_id: number
  name: string
  city: string
  state: string
  school_type: string
  url: string | null
  student_size: number | null
  tuition_in_state: number | null
  tuition_out_of_state: number | null
  avg_net_price: number | null
  net_price_by_income: Record<string, number | null> | null
  graduation_rate: number | null
  median_debt: number | null
  earnings_6yr: number | null
  earnings_10yr: number | null
  admission_rate: number | null
  retention_rate: number | null
  repayment_rate_3yr: number | null
}

/** GET /api/schools/[id]/programs */
export interface SchoolProgram {
  id: string
  school_id: number
  cip_code: string
  title: string
  credential_level: number
  earnings_1yr: number | null
  earnings_4yr: number | null
  median_debt: number | null
  /** ProgramDebt for the same field and credential, all schools */
  national_median_debt: number | null
  occupations: { id: string; name: string; annual_salary: number }[]
}

export const CREDENTIAL_LABELS: Record<number, string> = {
  1: 'Certificate',
  2: "Associate's",
  3: "Bachelor's",
  4: 'Post-bacc certificate',
  5: "Master's",
  6: 'Doctoral',
  7: 'Professional',
  8: 'Graduate certificate',
}
