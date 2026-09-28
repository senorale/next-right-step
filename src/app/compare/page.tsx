'use client'

import { useSearchParams } from 'next/navigation'
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Search } from 'lucide-react'
import Link from 'next/link'
import DegreePayoffComparison, {
  type ComparisonData,
} from '../components/compare/DegreePayoffComparison'
import PersonalPayoffCalculator, {
  type PersonalParams,
} from '../components/compare/PersonalPayoffCalculator'
import CompareDegreesTab from '../components/compare/CompareDegreesTab'
import { Input } from '@/components/ui/input'
import * as CollegeConstants from '@/app/constants/college_related_constants'

const DEFAULT_RATE = parseFloat(CollegeConstants.STUDENT_LOAN_INTEREST_RATE)
const DEFAULT_TERM = 20
const MAX_COMPARE = 3

interface OccupationLink {
  relevance: number
  occupation: { id: string; name: string; annual_salary: number; typical_years_of_school: number | null }
}

interface Degree {
  id: string
  name: string
  occupations: OccupationLink[]
}

interface ApiCompareResponse {
  degree: { id: string; name: string }
  weightedSalary: number
  weightedYears: number
  debt: ComparisonData['debt']
  availableCredentialLevels: number[]
}

function toComparisonData(data: ApiCompareResponse): ComparisonData {
  return {
    degree: data.degree,
    weightedSalary: data.weightedSalary,
    weightedYears: data.weightedYears,
    debt: data.debt,
  }
}

type Tab = 'program' | 'compare' | 'personal'

function CompareContent() {
  const searchParams = useSearchParams()
  const degreeIdParam = searchParams.get('majorId')
  const tabParam = searchParams.get('tab') as Tab | null

  const [allDegrees, setAllDegrees] = useState<Degree[]>([])
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState<Tab>(tabParam ?? 'program')

  // Program tab state
  const [selectedDegree, setSelectedDegree] = useState<Degree | null>(null)
  const [programData, setProgramData] = useState<ComparisonData | null>(null)
  const [personalParams, setPersonalParams] = useState<PersonalParams | null>(null)

  // Compare tab state
  const [compareDegrees, setCompareDegrees] = useState<ComparisonData[]>([])
  const [compareLoading, setCompareLoading] = useState(false)

  // Search state
  const [query, setQuery] = useState('')
  const initializedRef = useRef(false)

  useEffect(() => {
    fetch('/api/majors')
      .then((r) => r.json())
      .then((degrees: Degree[]) => {
        setAllDegrees(degrees)

        if (degreeIdParam) {
          const match = degrees.find((d: Degree) => d.id === degreeIdParam)
          if (match) {
            setSelectedDegree(match)
            loadDegree(match)
            return
          }
        }
        setLoading(false)
        initializedRef.current = true
      })
      .catch(() => setLoading(false))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [degreeIdParam])

  const loadDegree = useCallback((degree: Degree) => {
    setLoading(true)
    fetch(`/api/compare?majorId=${degree.id}`)
      .then((r) => r.json())
      .then((data: ApiCompareResponse) => {
        setProgramData(toComparisonData(data))

        const defaultDebt = data.debt?.all ?? data.debt?.public ?? data.debt?.privateNonprofit ?? 30000
        setPersonalParams({
          debt: defaultDebt,
          salary: data.weightedSalary,
          interestRate: DEFAULT_RATE,
          termYears: DEFAULT_TERM,
          yearsInSchool: Math.round(data.weightedYears),
        })

        const url = new URL(window.location.href)
        url.searchParams.set('majorId', degree.id)
        window.history.replaceState(null, '', url.toString())

        setLoading(false)
        initializedRef.current = true
      })
      .catch(() => setLoading(false))
  }, [])

  const addDegree = useCallback((degree: Degree) => {
    if (compareDegrees.some((d) => d.degree.id === degree.id)) return
    if (compareDegrees.length >= MAX_COMPARE) return

    setCompareLoading(true)
    fetch(`/api/compare?majorId=${degree.id}`)
      .then((r) => r.json())
      .then((data: ApiCompareResponse) => {
        setCompareDegrees((prev) => [...prev, toComparisonData(data)])
        setCompareLoading(false)
      })
      .catch(() => setCompareLoading(false))
  }, [compareDegrees])

  const removeDegree = useCallback((id: string) => {
    setCompareDegrees((prev) => prev.filter((d) => d.degree.id !== id))
  }, [])

  const handleSelect = useCallback(
    (d: Degree) => {
      setQuery('')
      if (tab === 'compare') {
        addDegree(d)
      } else {
        setSelectedDegree(d)
        loadDegree(d)
      }
    },
    [tab, addDegree, loadDegree]
  )

  const searchResults = useMemo(() => {
    if (query.trim().length < 2) return []
    const q = query.toLowerCase()
    const excludeIds = tab === 'compare'
      ? new Set(compareDegrees.map((d) => d.degree.id))
      : new Set<string>()
    return allDegrees
      .filter((d) => d.name.toLowerCase().includes(q) && !excludeIds.has(d.id))
      .slice(0, 8)
  }, [query, allDegrees, tab, compareDegrees])

  const handleTabChange = useCallback((newTab: Tab) => {
    setTab(newTab)
    setQuery('')
  }, [])

  if (loading && !initializedRef.current) {
    return (
      <div className="text-sm text-muted-foreground text-center py-6">
        Loading...
      </div>
    )
  }

  const atMax = tab === 'compare' && compareDegrees.length >= MAX_COMPARE
  const searchPlaceholder = tab === 'compare'
    ? atMax
      ? 'Remove one to add another'
      : `Add a degree (${compareDegrees.length}/${MAX_COMPARE})...`
    : selectedDegree
      ? selectedDegree.name
      : 'Search for a degree...'

  const showSearch = tab !== 'personal' || !programData

  return (
    <div className="space-y-6">
      {/* Tabs */}
      <div className="grid grid-cols-3 gap-1 rounded-lg border bg-muted/50 p-1">
        <TabButton active={tab === 'program'} onClick={() => handleTabChange('program')}>
          By program
        </TabButton>
        <TabButton active={tab === 'compare'} onClick={() => handleTabChange('compare')}>
          Compare degrees
        </TabButton>
        <TabButton active={tab === 'personal'} onClick={() => handleTabChange('personal')}>
          My numbers
        </TabButton>
      </div>

      {/* Search */}
      {showSearch && (
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={searchPlaceholder}
            disabled={atMax}
            className="pl-9"
          />
          {searchResults.length > 0 && (
            <div className="absolute z-10 mt-1 w-full overflow-hidden rounded-md border bg-popover shadow-md">
              {searchResults.map((d) => (
                <button
                  key={d.id}
                  onClick={() => handleSelect(d)}
                  className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-accent"
                >
                  <span className="truncate pr-2">{d.name}</span>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {d.occupations.length} occupations
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Tab content */}
      {tab === 'program' && (
        programData ? (
          <DegreePayoffComparison data={programData} />
        ) : (
          <p className="text-sm text-muted-foreground text-center py-8">
            Search for a degree to compare programs at public vs. private schools.
          </p>
        )
      )}

      {tab === 'compare' && (
        <>
          {compareLoading && (
            <div className="text-sm text-muted-foreground text-center py-2">Loading...</div>
          )}
          <CompareDegreesTab degrees={compareDegrees} onRemove={removeDegree} />
        </>
      )}

      {tab === 'personal' && (
        programData && personalParams ? (
          <PersonalPayoffCalculator
            params={personalParams}
            onParamsChange={setPersonalParams}
            degreeName={programData.degree.name}
          />
        ) : (
          <p className="text-sm text-muted-foreground text-center py-8">
            Search for a degree in the &ldquo;By program&rdquo; tab first, then switch here to adjust numbers.
          </p>
        )
      )}
    </div>
  )
}

function TabButton({
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

export default function ComparePage() {
  return (
    <main className="flex min-h-screen flex-col items-center p-4 sm:p-6 md:p-16">
      <div className="w-full max-w-2xl space-y-6">
        <div className="space-y-2">
          <Link href="/" className="text-sm text-primary hover:underline">
            ← Back
          </Link>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">
            Degree Payoff
          </h1>
          <p className="text-sm text-muted-foreground">
            Compare degree costs, debt, and break-even using real data or your own numbers.
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
