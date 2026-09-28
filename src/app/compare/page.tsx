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
import CompareMajorsTab from '../components/compare/CompareMajorsTab'
import { Input } from '@/components/ui/input'
import * as CollegeConstants from '@/app/constants/college_related_constants'

const DEFAULT_RATE = parseFloat(CollegeConstants.STUDENT_LOAN_INTEREST_RATE)
const DEFAULT_TERM = 20
const MAX_COMPARE = 3

interface OccupationLink {
  relevance: number
  occupation: { id: string; name: string; annual_salary: number; typical_years_of_school: number | null }
}

interface Major {
  id: string
  name: string
  occupations: OccupationLink[]
}

interface ApiCompareResponse {
  major: { id: string; name: string }
  weightedSalary: number
  weightedYears: number
  debt: ComparisonData['debt']
  availableCredentialLevels: number[]
}

type Tab = 'institution' | 'compare' | 'personal'

function CompareContent() {
  const searchParams = useSearchParams()
  const majorIdParam = searchParams.get('majorId')
  const tabParam = searchParams.get('tab') as Tab | null

  const [allMajors, setAllMajors] = useState<Major[]>([])
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState<Tab>(tabParam ?? 'institution')

  // Institution tab state
  const [selectedMajor, setSelectedMajor] = useState<Major | null>(null)
  const [compareData, setCompareData] = useState<ComparisonData | null>(null)
  const [personalParams, setPersonalParams] = useState<PersonalParams | null>(null)

  // Compare tab state
  const [compareMajors, setCompareMajors] = useState<ComparisonData[]>([])
  const [compareLoading, setCompareLoading] = useState(false)

  // Search state
  const [query, setQuery] = useState('')
  const initializedRef = useRef(false)

  useEffect(() => {
    fetch('/api/majors')
      .then((r) => r.json())
      .then((majors: Major[]) => {
        setAllMajors(majors)

        if (majorIdParam) {
          const match = majors.find((m: Major) => m.id === majorIdParam)
          if (match) {
            setSelectedMajor(match)
            loadSingleMajor(match)
            return
          }
        }
        setLoading(false)
        initializedRef.current = true
      })
      .catch(() => setLoading(false))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [majorIdParam])

  const loadSingleMajor = useCallback((major: Major) => {
    setLoading(true)
    fetch(`/api/compare?majorId=${major.id}`)
      .then((r) => r.json())
      .then((data: ApiCompareResponse) => {
        const comparison: ComparisonData = {
          major: data.major,
          weightedSalary: data.weightedSalary,
          weightedYears: data.weightedYears,
          debt: data.debt,
        }
        setCompareData(comparison)

        const defaultDebt = data.debt?.all ?? data.debt?.public ?? data.debt?.privateNonprofit ?? 30000
        setPersonalParams({
          debt: defaultDebt,
          salary: data.weightedSalary,
          interestRate: DEFAULT_RATE,
          termYears: DEFAULT_TERM,
          yearsInSchool: Math.round(data.weightedYears),
        })

        const url = new URL(window.location.href)
        url.searchParams.set('majorId', major.id)
        window.history.replaceState(null, '', url.toString())

        setLoading(false)
        initializedRef.current = true
      })
      .catch(() => setLoading(false))
  }, [])

  const addCompareMajor = useCallback((major: Major) => {
    if (compareMajors.some((m) => m.major.id === major.id)) return
    if (compareMajors.length >= MAX_COMPARE) return

    setCompareLoading(true)
    fetch(`/api/compare?majorId=${major.id}`)
      .then((r) => r.json())
      .then((data: ApiCompareResponse) => {
        const comparison: ComparisonData = {
          major: data.major,
          weightedSalary: data.weightedSalary,
          weightedYears: data.weightedYears,
          debt: data.debt,
        }
        setCompareMajors((prev) => [...prev, comparison])
        setCompareLoading(false)
      })
      .catch(() => setCompareLoading(false))
  }, [compareMajors])

  const removeCompareMajor = useCallback((id: string) => {
    setCompareMajors((prev) => prev.filter((m) => m.major.id !== id))
  }, [])

  const handleSelect = useCallback(
    (m: Major) => {
      setQuery('')
      if (tab === 'compare') {
        addCompareMajor(m)
      } else {
        setSelectedMajor(m)
        loadSingleMajor(m)
      }
    },
    [tab, addCompareMajor, loadSingleMajor]
  )

  const searchResults = useMemo(() => {
    if (query.trim().length < 2) return []
    const q = query.toLowerCase()
    const excludeIds = tab === 'compare'
      ? new Set(compareMajors.map((m) => m.major.id))
      : new Set<string>()
    return allMajors
      .filter((m) => m.name.toLowerCase().includes(q) && !excludeIds.has(m.id))
      .slice(0, 8)
  }, [query, allMajors, tab, compareMajors])

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

  const atMax = tab === 'compare' && compareMajors.length >= MAX_COMPARE
  const searchPlaceholder = tab === 'compare'
    ? atMax
      ? 'Remove one to add another'
      : `Add a major (${compareMajors.length}/${MAX_COMPARE})...`
    : selectedMajor
      ? selectedMajor.name
      : 'Search for a major...'

  const showSearch = tab !== 'personal' || !compareData

  return (
    <div className="space-y-6">
      {/* Tabs */}
      <div className="grid grid-cols-3 gap-1 rounded-lg border bg-muted/50 p-1">
        <TabButton active={tab === 'institution'} onClick={() => handleTabChange('institution')}>
          By institution
        </TabButton>
        <TabButton active={tab === 'compare'} onClick={() => handleTabChange('compare')}>
          Compare majors
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
              {searchResults.map((m) => (
                <button
                  key={m.id}
                  onClick={() => handleSelect(m)}
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
      )}

      {/* Tab content */}
      {tab === 'institution' && (
        compareData ? (
          <DegreePayoffComparison data={compareData} />
        ) : (
          <p className="text-sm text-muted-foreground text-center py-8">
            Search for a major to compare public vs. private school debt and break-even.
          </p>
        )
      )}

      {tab === 'compare' && (
        <>
          {compareLoading && (
            <div className="text-sm text-muted-foreground text-center py-2">Loading...</div>
          )}
          <CompareMajorsTab majors={compareMajors} onRemove={removeCompareMajor} />
        </>
      )}

      {tab === 'personal' && (
        compareData && personalParams ? (
          <PersonalPayoffCalculator
            params={personalParams}
            onParamsChange={setPersonalParams}
            majorName={compareData.major.name}
          />
        ) : (
          <p className="text-sm text-muted-foreground text-center py-8">
            Search for a major in the &ldquo;By institution&rdquo; tab first, then switch here to adjust numbers.
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
