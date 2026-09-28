'use client'

import { useEffect, useMemo, useState } from 'react'
import SearchDropdown from './SearchDropdown'
import { money } from './format'
import type { Occupation } from './types'

export default function OccupationSearch({
  onSelect,
  excludeIds = [],
  disabled,
  placeholder = 'Search occupations…',
}: {
  onSelect: (o: Occupation) => void
  excludeIds?: string[]
  disabled?: boolean
  placeholder?: string
}) {
  const [all, setAll] = useState<Occupation[]>([])
  const [query, setQuery] = useState('')

  useEffect(() => {
    fetch('/api/occupations/subcategories')
      .then((r) => r.json())
      .then((data: Occupation[]) => setAll(data))
      .catch(() => {})
  }, [])

  const matches = useMemo(() => {
    if (query.trim().length < 2) return []
    const q = query.toLowerCase()
    return all.filter((o) => o.name.toLowerCase().includes(q) && !excludeIds.includes(o.id)).slice(0, 8)
  }, [query, all, excludeIds])

  return (
    <SearchDropdown
      query={query}
      onQueryChange={setQuery}
      placeholder={placeholder}
      disabled={disabled}
      items={matches.map((o) => ({
        key: o.id,
        label: o.name,
        detail: money(o.annual_salary),
        onSelect: () => {
          onSelect(o)
          setQuery('')
        },
      }))}
    />
  )
}
