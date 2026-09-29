'use client'

import { useEffect, useMemo, useState } from 'react'
import SearchDropdown from './SearchDropdown'
import type { Degree } from './types'

export default function DegreeSearch({
  onSelect,
  placeholder = 'Search degrees…',
}: {
  onSelect: (d: Degree) => void
  placeholder?: string
}) {
  const [all, setAll] = useState<Degree[]>([])
  const [query, setQuery] = useState('')

  useEffect(() => {
    fetch('/api/degrees')
      .then((r) => r.json())
      .then((data: Degree[]) => setAll(data))
      .catch(() => {})
  }, [])

  const matches = useMemo(() => {
    if (query.trim().length < 2) return []
    const q = query.toLowerCase()
    return all.filter((d) => d.name.toLowerCase().includes(q)).slice(0, 8)
  }, [query, all])

  return (
    <SearchDropdown
      query={query}
      onQueryChange={setQuery}
      placeholder={placeholder}
      items={matches.map((d) => ({
        key: d.id,
        label: d.name,
        onSelect: () => {
          onSelect(d)
          setQuery('')
        },
      }))}
    />
  )
}
