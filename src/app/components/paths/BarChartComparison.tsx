'use client'

import { Bar, BarChart, Cell, LabelList, ResponsiveContainer, XAxis, YAxis } from 'recharts'

export interface BarDatum {
  name: string
  value: number | null
  color: string
}

/** Horizontal bars comparing one metric across items. Items with no value are listed below the chart. */
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
  const missing = data.filter((d) => d.value == null)
  const short = (name: string) => (name.length > 22 ? `${name.slice(0, 20)}…` : name)

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-semibold">{title}</h3>
      {withValues.length > 0 && (
        <ResponsiveContainer width="100%" height={withValues.length * 40 + 8}>
          <BarChart
            data={withValues.map((d) => ({ ...d, label: short(d.name) }))}
            layout="vertical"
            margin={{ left: 0, right: 72, top: 0, bottom: 0 }}
          >
            <XAxis type="number" hide domain={[0, 'dataMax']} />
            <YAxis type="category" dataKey="label" width={130} tick={{ fontSize: 12 }} />
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
      {missing.length > 0 && (
        <p className="text-xs text-muted-foreground">
          No data: {missing.map((d) => d.name).join(', ')}
        </p>
      )}
    </div>
  )
}
