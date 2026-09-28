'use client'

import { useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import PathHeader from '../components/paths/PathHeader'
import OccupationSearch from '../components/paths/OccupationSearch'
import DegreeSearch from '../components/paths/DegreeSearch'
import SelectedPills from '../components/paths/SelectedPills'
import PayoffSummary from '../components/paths/PayoffSummary'
import { computeFinancials, HS_SALARY } from '../components/paths/finance'
import { money, schoolYears } from '../components/paths/format'
import type { CareerCost, Degree, Occupation } from '../components/paths/types'
import { computeGap, HELD_CREDENTIALS, POSITIONS, type Position } from './gap'

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      role="radio"
      aria-checked={active}
      onClick={onClick}
      className={`rounded-full border px-3 py-1 text-sm transition-colors ${
        active ? 'border-primary bg-primary text-primary-foreground' : 'hover:bg-accent'
      }`}
    >
      {children}
    </button>
  )
}

export default function CareerPath() {
  const [target, setTarget] = useState<CareerCost | null>(null)
  const [loading, setLoading] = useState(false)
  const [position, setPosition] = useState<Position | null>(null)
  const [degree, setDegree] = useState<Degree | null>(null)
  const [yearsDone, setYearsDone] = useState(1)
  const [heldYears, setHeldYears] = useState(4)
  const [salary, setSalary] = useState<number | null>(null)

  const chooseTarget = async (o: Occupation) => {
    setLoading(true)
    const r = await fetch(`/api/career-cost?occupationId=${o.id}`)
    setTarget(r.ok ? await r.json() : null)
    setLoading(false)
  }

  const inSchool = position === 'in_college' || position === 'has_degree'
  const completedYears = position === 'in_college' ? yearsDone : position === 'has_degree' ? heldYears : 0
  const relevant = !!(target && degree && degree.occupationIds.includes(target.occupation.id))
  const gap = target && position ? computeGap({ cost: target, completedYears, relevant }) : null

  const hasIncome = position === 'working' && salary != null && salary > 0
  const currentIncome = hasIncome ? (salary as number) : HS_SALARY
  const incomeLabel = hasIncome ? 'your current salary' : 'a high school diploma'
  const financials =
    target && gap && gap.remainingCost !== null
      ? computeFinancials({
          debt: gap.remainingCost,
          yearsInSchool: gap.remainingYears,
          salary: target.occupation.annual_salary,
          baselineSalary: currentIncome,
        })
      : null

  const positionLabel = POSITIONS.find((p) => p.value === position)?.label

  return (
    <main className="flex min-h-screen flex-col items-center p-4 sm:p-6 md:p-16">
      <div className="w-full max-w-3xl space-y-6">
        <PathHeader
          title="Path to a career"
          description="Pick the career you want and tell us where you are now. We'll map the education left, what it costs, and how long until it pays off."
        />

        <Card>
          <CardHeader>
            <CardTitle className="text-lg">1. Target career</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {target ? (
              <SelectedPills
                items={[{ key: target.occupation.id, label: target.occupation.name }]}
                onRemove={() => setTarget(null)}
              />
            ) : (
              <OccupationSearch onSelect={chooseTarget} placeholder="Search careers, e.g. pharmacist…" />
            )}
            {loading && <p className="text-sm text-muted-foreground">Loading…</p>}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-lg">2. Where are you now?</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Current position">
              {POSITIONS.map((p) => (
                <Chip key={p.value} active={position === p.value} onClick={() => setPosition(p.value)}>
                  {p.label}
                </Chip>
              ))}
            </div>

            {inSchool && (
              <div className="space-y-3">
                <p className="text-sm font-medium">
                  {position === 'in_college' ? 'What are you studying?' : 'What is your degree in?'}
                </p>
                {degree ? (
                  <SelectedPills items={[{ key: degree.id, label: degree.name }]} onRemove={() => setDegree(null)} />
                ) : (
                  <DegreeSearch onSelect={setDegree} />
                )}

                {position === 'in_college' ? (
                  <div className="space-y-2">
                    <p className="text-sm font-medium">Years completed</p>
                    <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Years completed">
                      {[1, 2, 3].map((y) => (
                        <Chip key={y} active={yearsDone === y} onClick={() => setYearsDone(y)}>
                          {y}
                        </Chip>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <p className="text-sm font-medium">Highest degree</p>
                    <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Highest degree">
                      {HELD_CREDENTIALS.map((c) => (
                        <Chip key={c.years} active={heldYears === c.years} onClick={() => setHeldYears(c.years)}>
                          {c.label}
                        </Chip>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {position === 'working' && (
              <div className="space-y-2">
                <p className="text-sm font-medium">Current yearly salary (optional)</p>
                <Input
                  type="number"
                  inputMode="numeric"
                  min={0}
                  placeholder={`Leave blank to use ${money(HS_SALARY)}`}
                  value={salary ?? ''}
                  onChange={(e) => setSalary(e.target.value === '' ? null : Number(e.target.value))}
                />
              </div>
            )}
          </CardContent>
        </Card>

        {target && gap && (
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Your roadmap to {target.occupation.name}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              <ol className="space-y-4 border-l-2 pl-4">
                <li>
                  <p className="text-sm text-muted-foreground">Now</p>
                  <p className="font-medium">
                    {positionLabel}
                    {degree && inSchool ? `, ${degree.name}` : ''}
                    {hasIncome ? `, earning ${money(currentIncome)}/yr` : ''}
                  </p>
                </li>
                <li>
                  <p className="text-sm text-muted-foreground">Education</p>
                  <p className="font-medium">
                    {gap.requiredYears === 0
                      ? 'No degree required. You can start now.'
                      : gap.remainingYears === 0
                        ? `You already have the ${schoolYears(gap.requiredYears)} of school this career typically needs.`
                        : `${schoolYears(gap.remainingYears)} left of ${schoolYears(gap.requiredYears)} (${target.credentialLabel?.toLowerCase() ?? 'degree'})`}
                  </p>
                  {inSchool && degree && gap.requiredYears > 0 && (
                    <p className="text-sm text-muted-foreground">
                      {gap.relevant
                        ? `${degree.name} is a related field, so all ${schoolYears(completedYears)} count.`
                        : `${degree.name} is not a direct path to this career, so ${schoolYears(gap.creditedYears)} of it count.`}
                    </p>
                  )}
                  {target.degrees.length > 0 && gap.remainingYears > 0 && (
                    <p className="text-sm text-muted-foreground">
                      Related degrees: {target.degrees.slice(0, 4).map((d) => d.title).join(', ')}
                      {target.degrees.length > 4 ? ` and ${target.degrees.length - 4} more` : ''}
                    </p>
                  )}
                </li>
                <li>
                  <p className="text-sm text-muted-foreground">Estimated remaining cost</p>
                  <p className="font-medium">
                    {gap.remainingCost === null ? 'Cost data unavailable for this career' : money(gap.remainingCost)}
                  </p>
                </li>
                <li>
                  <p className="text-sm text-muted-foreground">Then</p>
                  <p className="font-medium">
                    {money(target.occupation.annual_salary)}/yr expected salary
                    {position === 'working' && (
                      <span className="text-muted-foreground">
                        {' '}
                        ({target.occupation.annual_salary >= currentIncome ? '+' : '-'}
                        {money(Math.abs(target.occupation.annual_salary - currentIncome))} vs now)
                      </span>
                    )}
                  </p>
                </li>
              </ol>

              {financials && (
                <PayoffSummary financials={financials} payoffLabel="Time to recoup" baselineLabel={incomeLabel} />
              )}
            </CardContent>
          </Card>
        )}

        <p className="text-center text-sm text-muted-foreground">
          Salaries: Bureau of Labor Statistics (May 2024), national medians, capped at $239,200/yr.
          Debt: College Scorecard. Years of school: O*NET typical education.
        </p>
      </div>
    </main>
  )
}
