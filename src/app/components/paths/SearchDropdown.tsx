'use client'

import { useId, useState, type KeyboardEvent, type ReactNode } from 'react'
import { Search } from 'lucide-react'
import { Input } from '@/components/ui/input'

export interface DropdownItem {
  key: string
  label: string
  detail?: ReactNode
  onSelect: () => void
}

/**
 * Search input with a results dropdown. Shared by the occupation, degree, and school searches.
 * Arrow keys move through results and Enter selects the highlighted one.
 */
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
  const listId = useId()
  const [active, setActive] = useState(0)
  const open = items.length > 0 || footer != null
  const activeIndex = Math.min(active, items.length - 1)

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (items.length === 0) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActive((activeIndex + 1) % items.length)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActive((activeIndex - 1 + items.length) % items.length)
    } else if (e.key === 'Enter') {
      e.preventDefault()
      items[activeIndex]?.onSelect()
      setActive(0)
    }
  }

  return (
    <div className="relative">
      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
      <Input
        value={query}
        onChange={(e) => {
          onQueryChange(e.target.value)
          setActive(0)
        }}
        onKeyDown={onKeyDown}
        placeholder={placeholder}
        disabled={disabled}
        className="pl-9"
        role="combobox"
        aria-expanded={items.length > 0}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={items.length > 0 ? `${listId}-${activeIndex}` : undefined}
      />
      {open && (
        <div className="absolute z-10 mt-1 w-full overflow-hidden rounded-md border bg-popover shadow-md">
          <div id={listId} role="listbox">
            {items.map((item, i) => (
              <button
                key={item.key}
                id={`${listId}-${i}`}
                role="option"
                aria-selected={i === activeIndex}
                tabIndex={-1}
                onClick={item.onSelect}
                onMouseEnter={() => setActive(i)}
                className={`flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm hover:bg-accent ${
                  i === activeIndex ? 'bg-accent' : ''
                }`}
              >
                <span className="min-w-0 break-words">{item.label}</span>
                {item.detail != null && (
                  <span className="shrink-0 tabular-nums text-muted-foreground">{item.detail}</span>
                )}
              </button>
            ))}
          </div>
          {footer}
        </div>
      )}
    </div>
  )
}
