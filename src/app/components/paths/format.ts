export const COLORS = [
  'hsl(var(--chart-1))',
  'hsl(var(--chart-2))',
  'hsl(var(--chart-3))',
  'hsl(var(--chart-4))',
  'hsl(var(--chart-5))',
]

export const colorAt = (i: number) => COLORS[i % COLORS.length]

export const money = (n: number) => `$${Math.round(n).toLocaleString()}`

export const moneyOrNA = (n: number | null | undefined) => (n == null ? 'n/a' : money(n))

export const pctOrNA = (n: number | null | undefined) => (n == null ? 'n/a' : `${Math.round(n * 100)}%`)

export const years = (n: number) => `${Math.round(n * 10) / 10} yrs`

export const schoolYears = (n: number | null | undefined) =>
  n == null ? 'n/a' : n === 0 ? 'None required' : `${n} yr${n === 1 ? '' : 's'}`

export const ratio = (n: number | null | undefined) => (n == null ? 'n/a' : `${(Math.round(n * 100) / 100).toFixed(2)}x`)
