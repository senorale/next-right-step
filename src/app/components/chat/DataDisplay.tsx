'use client'

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts'

const fmt = (n: number) => `$${Math.round(n).toLocaleString()}`
const pct = (n: number) => `${Math.round(n * 100)}%`
import type { ValueType, NameType } from 'recharts/types/component/DefaultTooltipContent'

const tooltipFmt = (v: ValueType | undefined, _name: NameType | undefined) => fmt(Number(v))

const COLORS = [
  'hsl(var(--primary))',
  'hsl(var(--chart-2, 173 58% 39%))',
  'hsl(var(--chart-3, 197 37% 24%))',
  'hsl(var(--chart-4, 43 74% 66%))',
  'hsl(var(--chart-5, 27 87% 67%))',
]

interface DataBlock {
  type: string
  data: unknown
}

function SchoolCard({ school }: { school: Record<string, unknown> }) {
  const gradRate = school.graduation_rate as number | null
  const netPrice = school.avg_net_price as number | null
  const earnings = school.earnings_10yr_after_entry as number | null
  const debt = school.median_debt as number | null
  const inState = school.tuition_in_state as number | null
  const outState = school.tuition_out_of_state as number | null
  const incomeData = school.net_price_by_income as Record<string, number | null> | null

  const costBars = [
    inState != null && { name: 'In-state', value: inState },
    outState != null && { name: 'Out-of-state', value: outState },
    netPrice != null && { name: 'Avg net price', value: netPrice },
  ].filter(Boolean) as { name: string; value: number }[]

  const incomeBars = incomeData
    ? [
        { name: '$0-30k', value: incomeData['0-30000'] },
        { name: '$30-48k', value: incomeData['30001-48000'] },
        { name: '$48-75k', value: incomeData['48001-75000'] },
        { name: '$75-110k', value: incomeData['75001-110000'] },
        { name: '$110k+', value: incomeData['110001-plus'] },
      ].filter((d) => d.value != null) as { name: string; value: number }[]
    : []

  return (
    <div className="rounded-lg border bg-card p-4 space-y-4">
      <div>
        <h3 className="font-semibold text-sm">{school.name as string}</h3>
        <p className="text-xs text-muted-foreground">
          {school.city as string}, {school.state as string} · {school.type as string}
        </p>
      </div>

      <div className="grid grid-cols-3 gap-3 text-center">
        {gradRate != null && (
          <div>
            <div className="text-lg font-bold text-primary">{pct(gradRate)}</div>
            <div className="text-xs text-muted-foreground">Grad rate</div>
          </div>
        )}
        {earnings != null && (
          <div>
            <div className="text-lg font-bold text-primary">{fmt(earnings)}</div>
            <div className="text-xs text-muted-foreground">Earnings (10yr)</div>
          </div>
        )}
        {debt != null && (
          <div>
            <div className="text-lg font-bold text-primary">{fmt(debt)}</div>
            <div className="text-xs text-muted-foreground">Median debt</div>
          </div>
        )}
      </div>

      {costBars.length > 0 && (
        <div>
          <p className="text-xs font-medium text-muted-foreground mb-1">Annual tuition</p>
          <ResponsiveContainer width="100%" height={costBars.length * 32 + 8}>
            <BarChart data={costBars} layout="vertical" margin={{ left: 0, right: 40, top: 0, bottom: 0 }}>
              <XAxis type="number" hide />
              <YAxis type="category" dataKey="name" width={90} tick={{ fontSize: 11 }} />
              <Tooltip formatter={tooltipFmt} />
              <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                {costBars.map((_, i) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {incomeBars.length > 0 && (
        <div>
          <p className="text-xs font-medium text-muted-foreground mb-1">Net price by family income</p>
          <ResponsiveContainer width="100%" height={incomeBars.length * 32 + 8}>
            <BarChart data={incomeBars} layout="vertical" margin={{ left: 0, right: 40, top: 0, bottom: 0 }}>
              <XAxis type="number" hide />
              <YAxis type="category" dataKey="name" width={70} tick={{ fontSize: 11 }} />
              <Tooltip formatter={tooltipFmt} />
              <Bar dataKey="value" radius={[0, 4, 4, 0]} fill={COLORS[1]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}

function ProgramsCard({ data }: { data: Record<string, unknown> }) {
  const schoolName = data.school_name as string
  const programs = data.programs as {
    title: string
    credential: string
    earnings_1yr_after_graduation: number | null
    earnings_4yr_after_graduation: number | null
  }[]

  if (!programs?.length) return null

  const top = programs.slice(0, 10)
  const chartData = top.map((p) => ({
    name: p.title.length > 30 ? p.title.slice(0, 28) + '…' : p.title,
    '1yr after grad': p.earnings_1yr_after_graduation ?? 0,
    '4yr after grad': p.earnings_4yr_after_graduation ?? 0,
  }))

  return (
    <div className="rounded-lg border bg-card p-4 space-y-4">
      <div>
        <h3 className="font-semibold text-sm">{schoolName} — Program Earnings</h3>
        <p className="text-xs text-muted-foreground">
          Top {top.length} programs by earnings after graduation
        </p>
      </div>

      <ResponsiveContainer width="100%" height={chartData.length * 36 + 24}>
        <BarChart data={chartData} layout="vertical" margin={{ left: 0, right: 40, top: 0, bottom: 0 }}>
          <XAxis type="number" hide />
          <YAxis type="category" dataKey="name" width={160} tick={{ fontSize: 10 }} />
          <Tooltip formatter={tooltipFmt} />
          <Bar dataKey="1yr after grad" radius={[0, 4, 4, 0]} fill={COLORS[0]} />
          <Bar dataKey="4yr after grad" radius={[0, 4, 4, 0]} fill={COLORS[1]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

function TuitionMediansCard({ data }: { data: Record<string, unknown>[] }) {
  const chartData = data.map((row) => ({
    name: (row.cohort as string).replace(/_/g, ' '),
    'Sticker price': (row.sticker_annual as number) ?? 0,
    'Net price': (row.net_price_annual as number) ?? 0,
  }))

  return (
    <div className="rounded-lg border bg-card p-4 space-y-4">
      <div>
        <h3 className="font-semibold text-sm">National Median Tuition</h3>
        <p className="text-xs text-muted-foreground">Sticker price vs. net price after aid</p>
      </div>

      <ResponsiveContainer width="100%" height={chartData.length * 48 + 24}>
        <BarChart data={chartData} layout="vertical" margin={{ left: 0, right: 40, top: 0, bottom: 0 }}>
          <XAxis type="number" hide />
          <YAxis type="category" dataKey="name" width={120} tick={{ fontSize: 11 }} />
          <Tooltip formatter={tooltipFmt} />
          <Bar dataKey="Sticker price" radius={[0, 4, 4, 0]} fill={COLORS[3]} />
          <Bar dataKey="Net price" radius={[0, 4, 4, 0]} fill={COLORS[0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

export default function DataDisplay({ blocks }: { blocks: DataBlock[] }) {
  if (!blocks?.length) return null

  return (
    <div className="space-y-3 w-full max-w-[85%]">
      {blocks.map((block, i) => {
        switch (block.type) {
          case 'search_schools': {
            const payload = block.data as { results: Record<string, unknown>[] }
            const schools = payload.results ?? []
            return schools.map((school, j) => (
              <SchoolCard key={`${i}-${j}`} school={school} />
            ))
          }
          case 'get_school_programs':
            return <ProgramsCard key={i} data={block.data as Record<string, unknown>} />
          case 'get_tuition_medians':
            return (
              <TuitionMediansCard
                key={i}
                data={block.data as Record<string, unknown>[]}
              />
            )
          default:
            return null
        }
      })}
    </div>
  )
}
