'use client'

import { Input } from '@/components/ui/input'
import OccupationSearch from './OccupationSearch'
import { HS_SALARY } from './finance'
import { money } from './format'
import type { Occupation } from './types'

export type Baseline =
  | { kind: 'hs' }
  | { kind: 'salary'; salary: number | null }
  | { kind: 'occupation'; occupation: Occupation | null }

export function baselineSalary(b: Baseline): number {
  if (b.kind === 'salary' && b.salary != null && b.salary > 0) return b.salary
  if (b.kind === 'occupation' && b.occupation) return b.occupation.annual_salary
  return HS_SALARY
}

export function baselineLabel(b: Baseline): string {
  if (b.kind === 'salary' && b.salary != null && b.salary > 0) return 'your current salary'
  if (b.kind === 'occupation' && b.occupation) return b.occupation.name
  return 'a high school diploma'
}

const MODES: { kind: Baseline['kind']; label: string }[] = [
  { kind: 'hs', label: 'High school diploma' },
  { kind: 'salary', label: 'My current salary' },
  { kind: 'occupation', label: 'My current job' },
]

/** Where the user is starting from. Salary gains and opportunity cost are measured against it. */
export default function BaselinePicker({ value, onChange }: { value: Baseline; onChange: (b: Baseline) => void }) {
  const select = (kind: Baseline['kind']) => {
    if (kind === value.kind) return
    onChange(kind === 'hs' ? { kind } : kind === 'salary' ? { kind, salary: null } : { kind, occupation: null })
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Starting point">
        {MODES.map((m) => (
          <button
            key={m.kind}
            role="radio"
            aria-checked={value.kind === m.kind}
            onClick={() => select(m.kind)}
            className={`rounded-full border px-3 py-1 text-sm transition-colors ${
              value.kind === m.kind ? 'border-primary bg-primary text-primary-foreground' : 'hover:bg-accent'
            }`}
          >
            {m.label}
          </button>
        ))}
      </div>

      {value.kind === 'salary' && (
        <Input
          type="number"
          inputMode="numeric"
          min={0}
          placeholder="Yearly salary, e.g. 42000"
          value={value.salary ?? ''}
          onChange={(e) => onChange({ kind: 'salary', salary: e.target.value === '' ? null : Number(e.target.value) })}
        />
      )}

      {value.kind === 'occupation' &&
        (value.occupation ? (
          <p className="text-sm">
            {value.occupation.name} · {money(value.occupation.annual_salary)}/yr{' '}
            <button
              onClick={() => onChange({ kind: 'occupation', occupation: null })}
              className="text-primary hover:underline"
            >
              Change
            </button>
          </p>
        ) : (
          <OccupationSearch
            onSelect={(o) => onChange({ kind: 'occupation', occupation: o })}
            placeholder="Search your current job…"
          />
        ))}

      <p className="text-xs text-muted-foreground">
        Comparing against {baselineLabel(value)} ({money(baselineSalary(value))}/yr).
      </p>
    </div>
  )
}
