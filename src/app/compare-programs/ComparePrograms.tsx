'use client'

import { useMemo, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import PathHeader from '../components/paths/PathHeader'
import SchoolSearch from '../components/paths/SchoolSearch'
import SearchDropdown from '../components/paths/SearchDropdown'
import SelectedPills from '../components/paths/SelectedPills'
import ComparisonTable, { bestIndex } from '../components/paths/ComparisonTable'
import BarChartComparison from '../components/paths/BarChartComparison'
import { colorAt, money, moneyOrNA, ratio } from '../components/paths/format'
import { CREDENTIAL_LABELS, type School, type SchoolProgram } from '../components/paths/types'

const MAX_PROGRAMS = 5

const programLabel = (p: SchoolProgram) => `${p.title} (${CREDENTIAL_LABELS[p.credential_level] ?? `Level ${p.credential_level}`})`

function median(values: number[]): number | null {
  if (values.length === 0) return null
  const s = [...values].sort((a, b) => a - b)
  const mid = Math.floor(s.length / 2)
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2
}

export default function ComparePrograms() {
  const [school, setSchool] = useState<School | null>(null)
  const [programs, setPrograms] = useState<SchoolProgram[]>([])
  const [status, setStatus] = useState<'idle' | 'loading' | 'error'>('idle')
  const [selected, setSelected] = useState<SchoolProgram[]>([])
  const [query, setQuery] = useState('')

  const chooseSchool = async (s: School) => {
    setSchool(s)
    setSelected([])
    setPrograms([])
    setStatus('loading')
    try {
      const r = await fetch(`/api/schools/${s.school_id}/programs`)
      if (!r.ok) throw new Error()
      const data: { programs: SchoolProgram[] } = await r.json()
      setPrograms(data.programs)
      setStatus('idle')
    } catch {
      setStatus('error')
    }
  }

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (q.length < 2) return []
    return programs
      .filter((p) => p.title.toLowerCase().includes(q) && !selected.some((s) => s.id === p.id))
      .slice(0, 10)
  }, [query, programs, selected])

  const rows = selected.map((p) => {
    const earnings = p.earnings_4yr ?? p.earnings_1yr
    const debt = p.median_debt ?? p.national_median_debt
    return {
      p,
      earnings,
      debt,
      debtIsNational: p.median_debt == null && p.national_median_debt != null,
      bls: median(p.occupations.map((o) => o.annual_salary)),
      earningsToDebt: earnings != null && debt != null && debt > 0 ? earnings / debt : null,
    }
  })
  const atMax = selected.length >= MAX_PROGRAMS

  return (
    <main className="flex min-h-screen flex-col items-center p-4 sm:p-6 md:p-16">
      <div className="w-full max-w-3xl space-y-6">
        <PathHeader
          title="Compare programs at a school"
          description="Pick your school, then compare what graduates of each program earn and borrow there."
        />

        <Card>
          <CardHeader>
            <CardTitle className="text-lg">1. Your school</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {school ? (
              <SelectedPills
                items={[{ key: String(school.school_id), label: `${school.name}, ${school.state}` }]}
                onRemove={() => {
                  setSchool(null)
                  setPrograms([])
                  setSelected([])
                }}
              />
            ) : (
              <SchoolSearch onSelect={chooseSchool} />
            )}
            {status === 'loading' && (
              <p className="text-sm text-muted-foreground">Loading programs from College Scorecard…</p>
            )}
            {status === 'error' && <p className="text-sm text-destructive">Could not load programs. Try again.</p>}
          </CardContent>
        </Card>

        {school && status === 'idle' && (
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">
                2. Programs to compare{' '}
                <span className="text-sm font-normal text-muted-foreground">
                  ({selected.length}/{MAX_PROGRAMS})
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {programs.length === 0 ? (
                <p className="text-sm text-muted-foreground">College Scorecard has no program data for this school.</p>
              ) : (
                <SearchDropdown
                  query={query}
                  onQueryChange={setQuery}
                  disabled={atMax}
                  placeholder={atMax ? 'Remove one to add another' : `Search ${programs.length} programs…`}
                  items={matches.map((p) => ({
                    key: p.id,
                    label: programLabel(p),
                    detail: p.earnings_4yr ?? p.earnings_1yr ? money((p.earnings_4yr ?? p.earnings_1yr) as number) : 'no earnings data',
                    onSelect: () => {
                      setSelected((prev) => [...prev, p])
                      setQuery('')
                    },
                  }))}
                />
              )}
              {selected.length > 0 && (
                <SelectedPills
                  items={selected.map((p) => ({ key: p.id, label: programLabel(p) }))}
                  onRemove={(id) => setSelected((prev) => prev.filter((p) => p.id !== id))}
                />
              )}
            </CardContent>
          </Card>
        )}

        {rows.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Side by side</CardTitle>
            </CardHeader>
            <CardContent>
              <ComparisonTable
                columns={rows.map((r, i) => ({ key: r.p.id, label: programLabel(r.p), color: colorAt(i) }))}
                rows={[
                  {
                    label: 'Earnings 1 yr after graduation',
                    info: 'Median earnings of this program\'s graduates at this school. Source: College Scorecard.',
                    values: rows.map((r) => moneyOrNA(r.p.earnings_1yr)),
                    best: bestIndex(rows.map((r) => r.p.earnings_1yr), true),
                  },
                  {
                    label: 'Earnings 4 yrs after graduation',
                    info: 'Median earnings of this program\'s graduates at this school. Source: College Scorecard.',
                    values: rows.map((r) => moneyOrNA(r.p.earnings_4yr)),
                    best: bestIndex(rows.map((r) => r.p.earnings_4yr), true),
                  },
                  {
                    label: 'National salary in related jobs',
                    info: 'Median of national salaries for occupations linked to this field. Source: Bureau of Labor Statistics.',
                    values: rows.map((r) => moneyOrNA(r.bls)),
                  },
                  {
                    label: 'Median debt',
                    info: 'Median federal debt of graduates at this school. Marked * when the school does not report it and the national median for the field is shown. Source: College Scorecard.',
                    values: rows.map((r) => (r.debt == null ? 'n/a' : `${money(r.debt)}${r.debtIsNational ? '*' : ''}`)),
                    best: bestIndex(rows.map((r) => r.debt), false),
                  },
                  {
                    label: 'Earnings-to-debt ratio',
                    info: 'Yearly earnings (4 yrs after graduation, else 1 yr) per dollar of median debt. Higher is better.',
                    values: rows.map((r) => ratio(r.earningsToDebt)),
                    best: bestIndex(rows.map((r) => r.earningsToDebt), true),
                  },
                  {
                    label: 'Related occupations',
                    values: rows.map((r) =>
                      r.p.occupations.length === 0 ? (
                        'n/a'
                      ) : (
                        <span key={r.p.id} className="text-xs font-normal">
                          {r.p.occupations.slice(0, 3).map((o) => o.name).join(', ')}
                        </span>
                      )
                    ),
                  },
                ]}
              />
            </CardContent>
          </Card>
        )}

        {rows.length > 0 && (
          <Card>
            <CardContent className="space-y-8 pt-6">
              <BarChartComparison
                title="Earnings-to-debt ratio"
                data={rows.map((r, i) => ({ name: programLabel(r.p), value: r.earningsToDebt, color: colorAt(i) }))}
                format={(v) => ratio(v)}
              />
              <BarChartComparison
                title="Earnings after graduation (4 yrs, else 1 yr)"
                data={rows.map((r, i) => ({ name: programLabel(r.p), value: r.earnings, color: colorAt(i) }))}
                format={money}
              />
            </CardContent>
          </Card>
        )}

        <p className="text-center text-sm text-muted-foreground">
          School program data: College Scorecard (school-specific). National salaries: Bureau of Labor Statistics (May 2024).
        </p>
      </div>
    </main>
  )
}
