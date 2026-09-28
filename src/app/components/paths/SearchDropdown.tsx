'use client'

import type { ReactNode } from 'react'
import { Search } from 'lucide-react'
import { Input } from '@/components/ui/input'

export interface DropdownItem {
  key: string
  label: string
  detail?: ReactNode
  onSelect: () => void
}

/** Search input with a results dropdown. Shared by the occupation, degree, and school searches. */
export default function SearchDropdown({
  query,
  onQueryChange,
  items,
  placeholder,
  disabled,
  footer,
}: {
  query: string
  onQueryChange: (q: string) => void
  items: DropdownItem[]
  placeholder: string
  disabled?: boolean
  footer?: ReactNode
}) {
  const open = items.length > 0 || footer != null
  return (
    <div className="relative">
      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
      <Input
        value={query}
        onChange={(e) => onQueryChange(e.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        className="pl-9"
      />
      {open && (
        <div className="absolute z-10 mt-1 w-full overflow-hidden rounded-md border bg-popover shadow-md">
          {items.map((item) => (
            <button
              key={item.key}
              onClick={item.onSelect}
              className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm hover:bg-accent"
            >
              <span className="min-w-0 truncate">{item.label}</span>
              {item.detail != null && (
                <span className="shrink-0 tabular-nums text-muted-foreground">{item.detail}</span>
              )}
            </button>
          ))}
          {footer}
        </div>
      )}
    </div>
  )
}
