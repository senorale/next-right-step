'use client'

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { X, Search, ChevronDown, ChevronUp } from 'lucide-react'
import { calculateTotalInterestPaid, calculateBreakEvenYears } from '../utils'
import * as C from '@/app/constants/college_related_constants'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

interface OccupationLink {
  relevance: number
  occupation: {
    id: string
    name: string
    annual_salary: number
    typical_years_of_school: number | null
  }
}

interface Major {
  id: string
  name: string
  occupations: OccupationLink[]
}

type Mode = 'compare' | 'breakeven'

const MAX_MAJORS = 4
const MEDIAN_DEBT = 39000
const MEDIAN_TERM_YEARS = 20
const DEFAULT_RATE = parseFloat(C.STUDENT_LOAN_INTEREST_RATE)
const DEFAULT_YEARS = parseFloat(C.BACHELOR_YEARS_IN_SCHOOL)
const DEFAULT_HS_SALARY = C.HIGHSCHOOL_DIPLOMA_MEDIAN_SALARY

const COLORS = [
  'hsl(var(--chart-1))',
  'hsl(var(--chart-2))',
  'hsl(var(--chart-3))',
  'hsl(var(--chart-4))',
]

const fmt = (n: number) => `$${Math.round(n).toLocaleString()}`
const num = (s: string) => {
  const n = parseFloat(s)
  return Number.isFinite(n) && n > 0 ? n : 0
}

function weightedMedianSalary(occupations: OccupationLink[]) {
  if (occupations.length === 0) return 0
  const totalWeight = occupations.reduce((s, o) => s + o.relevance, 0)
  return occupations.reduce((s, o) => s + o.occupation.annual_salary * o.relevance, 0) / totalWeight
}

function topSalary(occupations: OccupationLink[]) {
  return Math.max(0, ...occupations.map((o) => o.occupation.annual_salary))
}

function weightedYearsOfSchool(occupations: OccupationLink[]) {
  if (occupations.length === 0) return DEFAULT_YEARS
  const totalWeight = occupations.reduce((s, o) => s + o.relevance, 0)
  const avg = occupations.reduce(
    (s, o) => s + (o.occupation.typical_years_of_school ?? 4) * o.relevance, 0
  ) / totalWeight
  return Math.round(avg * 10) / 10
}

export default function CompareMajors() {
  const [mode, setMode] = useState<Mode>('compare')
  const [allMajors, setAllMajors] = useState<Major[]>([])
  const [selected, setSelected] = useState<Major[]>([])
  const [query, setQuery] = useState('')
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})

  const [annualTuition, setAnnualTuition] = useState('')
  const [amountBorrowed, setAmountBorrowed] = useState(String(MEDIAN_DEBT))
  const [rate, setRate] = useState(String(DEFAULT_RATE))
  const [term, setTerm] = useState(String(MEDIAN_TERM_YEARS))
  const [hsSalary, setHsSalary] = useState(String(DEFAULT_HS_SALARY))

  useEffect(() => {
    fetch('/api/majors')
      .then((r) => r.json())
      .then((data: Major[]) => setAllMajors(data))
      .catch(() => {})
    fetch('/api/tuition-medians')
      .then((r) => r.json())
      .then((meds: { cohort: string; net_price_annual: number | null; sticker_annual: number | null }[]) => {
        const inState = meds.find((m) => m.cohort === 'public_in_state')
        const annual = inState?.net_price_annual ?? inState?.sticker_annual
        if (annual) setAnnualTuition(String(annual))
      })
      .catch(() => {})
  }, [])

  const searchResults = useMemo(() => {
    if (query.trim().length < 2) return []
    const q = query.toLowerCase()
    return allMajors
      .filter((m) => m.name.toLowerCase().includes(q) && !selected.some((s) => s.id === m.id))
      .slice(0, 8)
  }, [query, allMajors, selected])

  const addMajor = (m: Major) => {
    if (selected.length < MAX_MAJORS) {
      setSelected((prev) => [...prev, m])
      setExpanded((prev) => ({ ...prev, [m.id]: true }))
      setQuery('')
    }
  }
  const removeMajor = (id: string) => setSelected((prev) => prev.filter((s) => s.id !== id))
  const toggleExpand = (id: string) => setExpanded((prev) => ({ ...prev, [id]: !prev[id] }))

  function investmentForYears(schoolYears: number) {
    const school = num(annualTuition) * schoolYears
    const interest = calculateTotalInterestPaid(num(amountBorrowed), num(rate), num(term))
    const opportunity = num(hsSalary) * schoolYears
    return { school, interest, opportunity, total: school + interest + opportunity }
  }

  const atMax = selected.length >= MAX_MAJORS
  const maxWeighted = Math.max(1, ...selected.map((m) => weightedMedianSalary(m.occupations)))

  return (
    <main className="flex min-h-screen flex-col items-center p-4 sm:p-6 md:p-16">
      <div className="w-full max-w-2xl space-y-6">
        <div className="space-y-2">
          <Link href="/" className="text-sm text-primary hover:underline">
            ← Back
          </Link>
          <h1 className="text-3xl font-bold tracking-tight">Compare majors</h1>
          <p className="text-sm text-muted-foreground">
            See which occupations each major leads to and what they pay.
          </p>
        </div>

        {/* Mode toggle */}
        <div className="grid grid-cols-2 gap-1 rounded-lg border bg-muted/50 p-1">
          <ModeButton active={mode === 'compare'} onClick={() => setMode('compare')}>
            Compare salaries
          </ModeButton>
          <ModeButton active={mode === 'breakeven'} onClick={() => setMode('breakeven')}>
            Will it pay off?
          </ModeButton>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="text-lg">
              Pick majors{' '}
              <span className="text-sm font-normal text-muted-foreground">
                ({selected.length}/{MAX_MAJORS})
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={atMax ? 'Remove one to add another' : 'Search majors…'}
                disabled={atMax}
                className="pl-9"
              />
              {searchResults.length > 0 && (
                <div className="absolute z-10 mt-1 w-full overflow-hidden rounded-md border bg-popover shadow-md">
                  {searchResults.map((m) => (
                    <button
                      key={m.id}
                      onClick={() => addMajor(m)}
                      className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-accent"
                    >
                      <span className="truncate pr-2">{m.name}</span>
                      <span className="shrink-0 text-xs text-muted-foreground">
                        {m.occupations.length} occupations
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>

            {selected.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {selected.map((m, i) => (
                  <span
                    key={m.id}
                    className="inline-flex items-center gap-1 rounded-full border px-3 py-1 text-sm"
                    style={{ borderColor: COLORS[i % COLORS.length] }}
                  >
                    {m.name}
                    <button
                      onClick={() => removeMajor(m.id)}
                      aria-label={`Remove ${m.name}`}
                      className="text-muted-foreground hover:text-foreground"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </span>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                Search and add up to {MAX_MAJORS} majors to compare.
              </p>
            )}
          </CardContent>
        </Card>

        {/* Break-even inputs */}
        {mode === 'breakeven' && (
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Your numbers</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm text-muted-foreground">
                Prefilled with national medians. Edit any to match your situation.
              </p>
              <div className="grid grid-cols-2 gap-4">
                <Field label="Annual tuition ($)" value={annualTuition} onChange={setAnnualTuition} />
                <Field label="Amount borrowed ($)" value={amountBorrowed} onChange={setAmountBorrowed} />
                <Field label="Loan interest rate (%)" value={rate} onChange={setRate} step="0.1" />
                <Field label="Repayment plan (years)" value={term} onChange={setTerm} />
                <Field label="Salary without degree ($)" value={hsSalary} onChange={setHsSalary} />
              </div>
              <p className="text-xs text-muted-foreground border-t pt-3">
                Years of school and total cost are calculated per field of study from O*NET education data.
              </p>
            </CardContent>
          </Card>
        )}

        {/* Results */}
        {selected.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">
                {mode === 'compare' ? 'Weighted average salary by major' : 'Years to pay off by major average salary'}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {mode === 'compare' && (
                <p className="text-xs text-muted-foreground">
                  Weighted by how directly the major leads to each occupation.
                </p>
              )}
              {[...selected]
                .sort((a, b) => weightedMedianSalary(b.occupations) - weightedMedianSalary(a.occupations))
                .map((m, i) => {
                  const weighted = weightedMedianSalary(m.occupations)
                  const top = topSalary(m.occupations)
                  const majorYears = weightedYearsOfSchool(m.occupations)
                  const isExpanded = expanded[m.id]
                  const investment = mode === 'breakeven' ? investmentForYears(majorYears) : null
                  const breakEven = investment
                    ? calculateBreakEvenYears(investment.total, weighted, num(hsSalary))
                    : null

                  return (
                    <div key={m.id} className="space-y-1">
                      <button
                        onClick={() => toggleExpand(m.id)}
                        className="flex w-full items-center justify-between text-sm"
                      >
                        <span className="flex items-center gap-1 truncate pr-2">
                          {m.name}
                          {isExpanded ? (
                            <ChevronUp className="h-3.5 w-3.5 text-muted-foreground" />
                          ) : (
                            <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                          )}
                        </span>
                        {mode === 'compare' ? (
                          <span className="shrink-0 font-semibold tabular-nums">
                            {fmt(weighted)}
                            <span className="font-normal text-muted-foreground ml-1 text-xs">
                              (top: {fmt(top)})
                            </span>
                          </span>
                        ) : (
                          <span className="shrink-0 text-right">
                            {typeof breakEven === 'number' ? (
                              <span className="font-bold">
                                {Math.round(breakEven * 10) / 10} yrs
                              </span>
                            ) : (
                              <span className="text-xs text-muted-foreground">
                                Pays ≤ no-degree salary
                              </span>
                            )}
                            <div className="text-xs text-muted-foreground">
                              {majorYears}yr school · {fmt(weighted)}/yr · {fmt(investment!.total)} total
                            </div>
                          </span>
                        )}
                      </button>
                      {mode === 'compare' && (
                        <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                          <div
                            className="h-full rounded-full"
                            style={{
                              width: `${(weighted / maxWeighted) * 100}%`,
                              backgroundColor: COLORS[i % COLORS.length],
                            }}
                          />
                        </div>
                      )}
                      {isExpanded && (
                        <div className="mt-2 space-y-2 pl-2 border-l-2 ml-1" style={{ borderColor: COLORS[i % COLORS.length] }}>
                          {m.occupations.map((o) => (
                            <div key={o.occupation.id} className="flex items-center justify-between text-xs">
                              <span className="truncate pr-2 text-muted-foreground">
                                {o.occupation.name}
                              </span>
                              <span className="shrink-0 tabular-nums">
                                {fmt(o.occupation.annual_salary)}
                              </span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )
                })}
            </CardContent>
          </Card>
        )}

        <p className="text-center text-sm text-muted-foreground">
          Salary data from the Bureau of Labor Statistics (May 2024).
          The BLS caps reported salaries at $239,200/yr, so some occupations
          (e.g. surgeons, physicians) earn more than shown.{' '}
          <Link href="/faq" className="text-primary hover:underline">
            Read the FAQ →
          </Link>
        </p>
      </div>
    </main>
  )
}

function ModeButton({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      onClick={onClick}
      className={`rounded-md px-3 py-2 text-sm font-medium transition-colors ${
        active ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'
      }`}
    >
      {children}
    </button>
  )
}

function Field({
  label,
  value,
  onChange,
  step,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  step?: string
}) {
  return (
    <div className="space-y-1">
      <Label className="text-xs text-muted-foreground">{label}</Label>
      <Input
        type="number"
        min={0}
        step={step}
        value={value}
        onChange={(e) => onChange(e.target.value)}
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
