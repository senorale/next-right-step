'use client'

import { Bar, BarChart, Cell, LabelList, ResponsiveContainer, XAxis, YAxis } from 'recharts'

export interface BarDatum {
  name: string
  value: number | null
  color: string
  /** Why value is null, e.g. "Does not pay off". Defaults to "No data". */
  note?: string
}

const LABEL_WIDTH = 130
const LINE_CHARS = 20
const MAX_LINES = 3
const LINE_HEIGHT = 14

/** Word-wraps a label into at most MAX_LINES lines, ellipsizing the last one. */
function wrap(name: string): string[] {
  const lines: string[] = []
  let line = ''
  for (const word of name.split(/\s+/)) {
    if (line && (line + ' ' + word).length > LINE_CHARS) {
      lines.push(line)
      line = word
    } else {
      line = line ? `${line} ${word}` : word
    }
  }
  if (line) lines.push(line)
  if (lines.length <= MAX_LINES) return lines
  const kept = lines.slice(0, MAX_LINES)
  const last = kept[MAX_LINES - 1]
  kept[MAX_LINES - 1] = `${last.slice(0, LINE_CHARS - 1)}…`
  return kept
}

function WrappedTick({ x, y, payload }: { x?: number; y?: number; payload?: { value: string } }) {
  const name = payload?.value ?? ''
  const lines = wrap(name)
  const top = -((lines.length - 1) * LINE_HEIGHT) / 2
  return (
    <text x={x} y={y} textAnchor="end" fontSize={12} className="fill-muted-foreground">
      <title>{name}</title>
      {lines.map((l, i) => (
        <tspan key={i} x={x} dx={-6} dy={i === 0 ? top + 4 : LINE_HEIGHT}>
          {l}
        </tspan>
      ))}
    </text>
  )
}

/** Horizontal bars comparing one metric across items. Items with no value are listed below the chart, grouped by note. */
export default function BarChartComparison({
  title,
  data,
  format,
}: {
  title: string
  data: BarDatum[]
  format: (v: number) => string
}) {
  const withValues = data.filter((d): d is BarDatum & { value: number } => d.value != null)
  const missing = new Map<string, string[]>()
  for (const d of data) {
    if (d.value != null) continue
    const note = d.note ?? 'No data'
    missing.set(note, [...(missing.get(note) ?? []), d.name])
  }
  const rowHeight = Math.max(40, ...withValues.map((d) => wrap(d.name).length * LINE_HEIGHT + 12))

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-semibold">{title}</h3>
      {withValues.length > 0 && (
        <ResponsiveContainer width="100%" height={withValues.length * rowHeight + 8}>
          <BarChart data={withValues} layout="vertical" margin={{ left: 0, right: 72, top: 0, bottom: 0 }}>
            <XAxis type="number" hide domain={[0, 'dataMax']} />
            <YAxis type="category" dataKey="name" width={LABEL_WIDTH} tick={<WrappedTick />} interval={0} />
            <Bar dataKey="value" radius={[0, 4, 4, 0]} barSize={24} isAnimationActive={false}>
              {withValues.map((d) => (
                <Cell key={d.name} fill={d.color} />
              ))}
              <LabelList
                dataKey="value"
                position="right"
                formatter={(v) => format(Number(v))}
                className="fill-foreground text-xs"
              />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}
      {[...missing].map(([note, names]) => (
        <p key={note} className="text-xs text-muted-foreground">
          {note}: {names.join(', ')}
        </p>
      ))}
    </div>
  )
}
