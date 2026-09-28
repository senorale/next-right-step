'use client'

import { useEffect, useState } from 'react'
import SearchDropdown from './SearchDropdown'
import type { School } from './types'

const DEBOUNCE_MS = 250

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
      fetch(`/api/schools/search?name=${encodeURIComponent(q)}`, { signal: controller.signal })
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
  }, [query])

  const searchScorecard = async () => {
    setLiveState('loading')
    try {
      const r = await fetch(`/api/schools/search?name=${encodeURIComponent(searched)}&live=1`)
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
          </div>
        ) : undefined
      }
    />
  )
}
