'use client'

import { X } from 'lucide-react'
import { colorAt } from './format'

export default function SelectedPills({
  items,
  onRemove,
}: {
  items: { key: string; label: string }[]
  onRemove: (key: string) => void
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {items.map((item, i) => (
        <span
          key={item.key}
          className="inline-flex max-w-full items-center gap-1 rounded-full border-2 px-3 py-1 text-sm"
          style={{ borderColor: colorAt(i) }}
        >
          <span className="truncate">{item.label}</span>
          <button
            onClick={() => onRemove(item.key)}
            aria-label={`Remove ${item.label}`}
            className="text-muted-foreground hover:text-foreground"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </span>
      ))}
    </div>
  )
}
