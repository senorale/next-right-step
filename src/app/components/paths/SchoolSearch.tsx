'use client'

import { useEffect, useState } from 'react'
import SearchDropdown from './SearchDropdown'
import { US_STATES } from './states'
import type { School } from './types'

const DEBOUNCE_MS = 250
const ALL_STATES = 'all'

function searchUrl(name: string, state: string, live = false): string {
  const params = new URLSearchParams({ name })
  if (state !== ALL_STATES) params.set('state', state)
  if (live) params.set('live', '1')
  return `/api/schools/search?${params}`
}

/**
 * Typeahead against the local School table. When nothing matches, offers a
 * College Scorecard lookup, which stores what it finds for next time.
 */
export default function SchoolSearch({
  onSelect,
  excludeIds = [],
  disabled,
  placeholder = 'Search schools by name…',
}: {
  onSelect: (s: School) => void
  excludeIds?: number[]
  disabled?: boolean
  placeholder?: string
}) {
  const [query, setQuery] = useState('')
  const [state, setState] = useState(ALL_STATES)
  const [results, setResults] = useState<School[]>([])
  const [searched, setSearched] = useState('')
  const [liveState, setLiveState] = useState<'idle' | 'loading' | 'empty' | 'error'>('idle')

  useEffect(() => {
    const q = query.trim()
    if (q.length < 2) {
      setResults([])
      setSearched('')
      return
    }
    const controller = new AbortController()
    const timer = setTimeout(() => {
      fetch(searchUrl(q, state), { signal: controller.signal })
        .then((r) => r.json())
        .then((data: { results?: School[] }) => {
          setResults(data.results ?? [])
          setSearched(q)
          setLiveState('idle')
        })
        .catch(() => {})
    }, DEBOUNCE_MS)
    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [query, state])

  const searchScorecard = async () => {
    setLiveState('loading')
    try {
      const r = await fetch(searchUrl(searched, state, true))
      const data: { results?: School[] } = await r.json()
      setResults(data.results ?? [])
      setLiveState(data.results?.length ? 'idle' : 'empty')
    } catch {
      setLiveState('error')
    }
  }

  const select = (s: School) => {
    onSelect(s)
    setQuery('')
    setResults([])
    setSearched('')
  }

  const visible = results.filter((s) => !excludeIds.includes(s.school_id))
  const noMatch = searched.length >= 2 && searched === query.trim() && results.length === 0

  return (
    <div className="flex flex-col gap-2 sm:flex-row">
      <select
        value={state}
        onChange={(e) => setState(e.target.value)}
        disabled={disabled}
        aria-label="Filter by state"
        className="h-10 rounded-md border border-input bg-white px-3 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 sm:w-48"
      >
        <option value={ALL_STATES}>All states</option>
        {US_STATES.map((s) => (
          <option key={s.code} value={s.code}>
            {s.name}
          </option>
        ))}
      </select>
      <div className="flex-1">
        <SearchDropdown
          query={query}
          onQueryChange={setQuery}
          placeholder={placeholder}
          disabled={disabled}
          items={visible.map((s) => ({
            key: String(s.school_id),
            label: s.name,
            detail: `${s.city}, ${s.state} · ${s.school_type}`,
            onSelect: () => select(s),
          }))}
          footer={
            noMatch ? (
              <div className="space-y-2 px-3 py-2 text-sm">
                {liveState === 'empty' ? (
                  <p className="text-muted-foreground">No schools found for &ldquo;{searched}&rdquo;.</p>
                ) : liveState === 'error' ? (
                  <p className="text-destructive">Search failed. Try again.</p>
                ) : (
                  <>
                    <p className="text-muted-foreground">Not in our list yet.</p>
                    <button
                      onClick={searchScorecard}
                      disabled={liveState === 'loading'}
                      className="text-primary hover:underline disabled:opacity-50"
                    >
                      {liveState === 'loading' ? 'Searching College Scorecard…' : 'Search College Scorecard'}
                    </button>
                  </>
                )}
                <p className="text-xs text-muted-foreground">
                  Use full words, not abbreviations. For example, &ldquo;Santa Barbara&rdquo; or &ldquo;University of
                  California&rdquo;, not &ldquo;UCSB&rdquo; or &ldquo;UC Santa Barbara&rdquo;. School names come from the
                  U.S. Department of Education.
                </p>
              </div>
            ) : undefined
          }
        />
      </div>
    </div>
  )
}
