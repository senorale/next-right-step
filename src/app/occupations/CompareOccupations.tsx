'use client'

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { X, Search } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'

interface Occupation {
  id: string
  name: string
  annual_salary: number
  typical_years_of_school: number | null
}

const MAX_OCCUPATIONS = 5

const COLORS = [
  'hsl(var(--chart-1))',
  'hsl(var(--chart-2))',
  'hsl(var(--chart-3))',
  'hsl(var(--chart-4))',
  'hsl(var(--chart-5))',
]

const fmt = (n: number) => `$${Math.round(n).toLocaleString()}`

export default function CompareOccupations() {
  const [all, setAll] = useState<Occupation[]>([])
  const [selected, setSelected] = useState<Occupation[]>([])
  const [query, setQuery] = useState('')

  useEffect(() => {
    fetch('/api/occupations/subcategories')
      .then((r) => r.json())
      .then((data: Occupation[]) => setAll(data))
      .catch(() => {})
  }, [])

  const searchResults = useMemo(() => {
    if (query.trim().length < 2) return []
    const q = query.toLowerCase()
    return all
      .filter((o) => o.name.toLowerCase().includes(q) && !selected.some((s) => s.id === o.id))
      .slice(0, 8)
  }, [query, all, selected])

  const addOccupation = (o: Occupation) => {
    if (selected.length < MAX_OCCUPATIONS) {
      setSelected((prev) => [...prev, o])
      setQuery('')
    }
  }
  const removeOccupation = (id: string) => setSelected((prev) => prev.filter((s) => s.id !== id))

  const atMax = selected.length >= MAX_OCCUPATIONS
  const maxSalary = Math.max(1, ...selected.map((o) => o.annual_salary))

  return (
    <main className="flex min-h-screen flex-col items-center p-4 sm:p-6 md:p-16">
      <div className="w-full max-w-2xl space-y-6">
        <div className="space-y-2">
          <Link href="/" className="text-sm text-primary hover:underline">
            ← Back
          </Link>
          <h1 className="text-3xl font-bold tracking-tight">Compare occupations</h1>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="text-lg">
              Pick occupations{' '}
              <span className="text-sm font-normal text-muted-foreground">
                ({selected.length}/{MAX_OCCUPATIONS})
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={atMax ? 'Remove one to add another' : 'Search occupations…'}
                disabled={atMax}
                className="pl-9"
              />
              {searchResults.length > 0 && (
                <div className="absolute z-10 mt-1 w-full overflow-hidden rounded-md border bg-popover shadow-md">
                  {searchResults.map((o) => (
                    <button
                      key={o.id}
                      onClick={() => addOccupation(o)}
                      className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-accent"
                    >
                      <span className="truncate pr-2">{o.name}</span>
                      <span className="shrink-0 tabular-nums text-muted-foreground">
                        {fmt(o.annual_salary)}
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>

            {selected.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {selected.map((o, i) => (
                  <span
                    key={o.id}
                    className="inline-flex items-center gap-1 rounded-full border px-3 py-1 text-sm"
                    style={{ borderColor: COLORS[i % COLORS.length] }}
                  >
                    {o.name}
                    <button
                      onClick={() => removeOccupation(o.id)}
                      aria-label={`Remove ${o.name}`}
                      className="text-muted-foreground hover:text-foreground"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </span>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                Search and add up to {MAX_OCCUPATIONS} occupations to compare.
              </p>
            )}
          </CardContent>
        </Card>

        {selected.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">National median annual salary</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {[...selected]
                .sort((a, b) => b.annual_salary - a.annual_salary)
                .map((o, i) => (
                  <div key={o.id} className="space-y-1">
                    <div className="flex items-center justify-between text-sm">
                      <span className="truncate pr-2">{o.name}</span>
                      <span className="shrink-0 font-semibold tabular-nums">
                        {fmt(o.annual_salary)}
                      </span>
                    </div>
                    {o.typical_years_of_school != null && (
                      <div className="text-xs text-muted-foreground">
                        {o.typical_years_of_school === 0
                          ? 'No degree required'
                          : `${o.typical_years_of_school}yr of school`}
                      </div>
                    )}
                    <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                      <div
                        className="h-full rounded-full"
                        style={{
                          width: `${(o.annual_salary / maxSalary) * 100}%`,
                          backgroundColor: COLORS[i % COLORS.length],
                        }}
                      />
                    </div>
                  </div>
                ))}
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
