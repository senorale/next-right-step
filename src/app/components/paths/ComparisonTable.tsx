import type { ReactNode } from 'react'
import { InfoTooltip } from '../calculator/InfoTooltip'
import { colorAt } from './format'

export interface ComparisonRow {
  label: string
  info?: string
  values: ReactNode[]
  /** Index of the column to highlight as best for this row. */
  best?: number | null
}

/** Metrics down the side, compared items across the top. Scrolls sideways on narrow screens. */
export default function ComparisonTable({
  columns,
  rows,
}: {
  columns: { key: string; label: string; color?: string }[]
  rows: ComparisonRow[]
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr>
            <th className="sticky left-0 bg-card" />
            {columns.map((c, i) => (
              <th
                key={c.key}
                className="min-w-[8rem] border-b-2 px-3 py-2 text-left align-bottom font-semibold"
                style={{ borderColor: c.color ?? colorAt(i) }}
              >
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.label} className="border-b last:border-0">
              <th
                scope="row"
                className="sticky left-0 min-w-[9rem] bg-card py-2 pr-3 text-left font-normal text-muted-foreground"
              >
                {row.label}
                {row.info && <InfoTooltip content={row.info} />}
              </th>
              {row.values.map((v, i) => (
                <td
                  key={columns[i]?.key ?? i}
                  className={`px-3 py-2 tabular-nums ${row.best === i ? 'font-semibold text-primary' : ''}`}
                >
                  {v}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** Index of the best numeric value (ignoring nulls), or null when fewer than two values exist. */
export function bestIndex(values: (number | null)[], higherIsBetter: boolean): number | null {
  let best: number | null = null
  let count = 0
  values.forEach((v, i) => {
    if (v == null) return
    count++
    if (best === null) {
      best = i
      return
    }
    const current = values[best] as number
    if (higherIsBetter ? v > current : v < current) best = i
  })
  return count >= 2 ? best : null
}
