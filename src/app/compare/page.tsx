'use client'

import { useSearchParams } from 'next/navigation'
import { Suspense, useCallback, useEffect, useMemo, useRef, useState, type DependencyList } from 'react'
import { Search } from 'lucide-react'
import Link from 'next/link'
import DegreePayoffComparison, {
  type ComparisonData,
  type ComparisonParams,
} from '../components/compare/DegreePayoffComparison'
import { Input } from '@/components/ui/input'
import * as CollegeConstants from '@/app/constants/college_related_constants'

const DEFAULT_RATE = parseFloat(CollegeConstants.STUDENT_LOAN_INTEREST_RATE)
const DEFAULT_TERM = 20

interface OccupationLink {
  relevance: number
  occupation: { id: string; name: string; annual_salary: number; typical_years_of_school: number | null }
}

interface Major {
  id: string
  name: string
  occupations: OccupationLink[]
}

interface TuitionDefaults {
  publicInState: number
  privateNonprofit: number
}

function weightedSalary(occupations: OccupationLink[]) {
  if (occupations.length === 0) return 0
  const totalWeight = occupations.reduce((s, o) => s + o.relevance, 0)
  return Math.round(
    occupations.reduce((s, o) => s + o.occupation.annual_salary * o.relevance, 0) / totalWeight
  )
}

function weightedYears(occupations: OccupationLink[]) {
  if (occupations.length === 0) return 4
  const totalWeight = occupations.reduce((s, o) => s + o.relevance, 0)
  const avg = occupations.reduce(
    (s, o) => s + (o.occupation.typical_years_of_school ?? 4) * o.relevance, 0
  ) / totalWeight
  return Math.round(avg * 10) / 10
}

function useDebouncedCallback<T extends (...args: never[]) => void>(
  fn: T,
  delay: number,
  deps: DependencyList
): T {
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  return useCallback(
    ((...args: Parameters<T>) => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current)
      timeoutRef.current = setTimeout(() => fn(...args), delay)
    }) as T,
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [delay, ...deps]
  )
}

function readParam(params: URLSearchParams, key: string): number | null {
  const v = params.get(key)
  if (v == null) return null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

function CompareContent() {
  const searchParams = useSearchParams()
  const majorIdParam = searchParams.get('majorId')

  const [allMajors, setAllMajors] = useState<Major[]>([])
  const [tuitionDefaults, setTuitionDefaults] = useState<TuitionDefaults | null>(null)
  const [selectedMajor, setSelectedMajor] = useState<Major | null>(null)
  const [params, setParams] = useState<ComparisonParams | null>(null)
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const initializedRef = useRef(false)

  useEffect(() => {
    Promise.all([
      fetch('/api/majors').then((r) => r.json()),
      fetch('/api/tuition-medians').then((r) => r.json()),
    ])
      .then(([majors, medians]: [Major[], { cohort: string; net_price_annual: number | null; sticker_annual: number | null }[]]) => {
        setAllMajors(majors)

        const pub = medians.find((m) => m.cohort === 'public_in_state')
        const priv = medians.find((m) => m.cohort === 'private_nonprofit')
        const defaults: TuitionDefaults = {
          publicInState: pub?.net_price_annual ?? pub?.sticker_annual ?? 0,
          privateNonprofit: priv?.net_price_annual ?? priv?.sticker_annual ?? 0,
        }
        setTuitionDefaults(defaults)

        if (majorIdParam) {
          const match = majors.find((m: Major) => m.id === majorIdParam)
          if (match) {
            setSelectedMajor(match)
            setParams({
              salary: readParam(searchParams, 'salary') ?? weightedSalary(match.occupations),
              publicTuition: readParam(searchParams, 'publicTuition') ?? defaults.publicInState,
              privateTuition: readParam(searchParams, 'privateTuition') ?? defaults.privateNonprofit,
              interestRate: readParam(searchParams, 'rate') ?? DEFAULT_RATE,
              termYears: readParam(searchParams, 'term') ?? DEFAULT_TERM,
            })
          }
        }

        initializedRef.current = true
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [majorIdParam, searchParams])

  const updateUrl = useDebouncedCallback(
    (majorId: string, p: ComparisonParams, defaults: TuitionDefaults, defaultSalary: number) => {
      const url = new URL(window.location.href)
      url.searchParams.set('majorId', majorId)

      const conditionalParams: [string, number, number][] = [
        ['salary', p.salary, defaultSalary],
        ['publicTuition', p.publicTuition, defaults.publicInState],
        ['privateTuition', p.privateTuition, defaults.privateNonprofit],
        ['rate', p.interestRate, DEFAULT_RATE],
        ['term', p.termYears, DEFAULT_TERM],
      ]
      for (const [key, value, defaultValue] of conditionalParams) {
        if (value !== defaultValue) {
          url.searchParams.set(key, String(value))
        } else {
          url.searchParams.delete(key)
        }
      }

      window.history.replaceState(null, '', url.toString())
    },
    500,
    []
  )

  const selectMajor = useCallback(
    (m: Major) => {
      setSelectedMajor(m)
      setQuery('')
      if (!tuitionDefaults) return
      const defaultSalary = weightedSalary(m.occupations)
      const newParams: ComparisonParams = {
        salary: defaultSalary,
        publicTuition: tuitionDefaults.publicInState,
        privateTuition: tuitionDefaults.privateNonprofit,
        interestRate: DEFAULT_RATE,
        termYears: DEFAULT_TERM,
      }
      setParams(newParams)
      updateUrl(m.id, newParams, tuitionDefaults, defaultSalary)
    },
    [tuitionDefaults, updateUrl]
  )

  const handleParamsChange = useCallback(
    (newParams: ComparisonParams) => {
      setParams(newParams)
      if (selectedMajor && tuitionDefaults) {
        updateUrl(selectedMajor.id, newParams, tuitionDefaults, weightedSalary(selectedMajor.occupations))
      }
    },
    [selectedMajor, tuitionDefaults, updateUrl]
  )

  const searchResults = useMemo(() => {
    if (query.trim().length < 2) return []
    const q = query.toLowerCase()
    return allMajors
      .filter((m) => m.name.toLowerCase().includes(q))
      .slice(0, 8)
  }, [query, allMajors])

  if (loading) {
    return (
      <div className="text-sm text-muted-foreground text-center py-6">
        Loading...
      </div>
    )
  }

  const comparisonData: ComparisonData | null =
    selectedMajor && tuitionDefaults
      ? {
          major: { id: selectedMajor.id, name: selectedMajor.name },
          weightedSalary: weightedSalary(selectedMajor.occupations),
          weightedYears: weightedYears(selectedMajor.occupations),
          tuition: tuitionDefaults,
        }
      : null

  return (
    <div className="space-y-6">
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={selectedMajor ? selectedMajor.name : 'Search for a major...'}
          className="pl-9"
        />
        {searchResults.length > 0 && (
          <div className="absolute z-10 mt-1 w-full overflow-hidden rounded-md border bg-popover shadow-md">
            {searchResults.map((m) => (
              <button
                key={m.id}
                onClick={() => selectMajor(m)}
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

      {comparisonData && params ? (
        <DegreePayoffComparison
          data={comparisonData}
          params={params}
          onParamsChange={handleParamsChange}
        />
      ) : (
        <p className="text-sm text-muted-foreground text-center py-8">
          Search for a major above to see a side-by-side loan comparison between public and private schools.
        </p>
      )}
    </div>
  )
}

export default function ComparePage() {
  return (
    <main className="flex min-h-screen flex-col items-center p-4 sm:p-6 md:p-16">
      <div className="w-full max-w-2xl space-y-6">
        <div className="space-y-2">
          <Link href="/" className="text-sm text-primary hover:underline">
            ← Back
          </Link>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">
            Degree Payoff Comparison
          </h1>
          <p className="text-sm text-muted-foreground">
            Compare the cost of a degree at a public vs. private school and see how long it takes to pay off.
          </p>
        </div>
        <Suspense
          fallback={
            <div className="text-sm text-muted-foreground text-center py-6">
              Loading...
            </div>
          }
        >
          <CompareContent />
        </Suspense>
      </div>
    </main>
  )
}
