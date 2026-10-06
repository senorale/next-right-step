'use client'

import { useState, useRef, useEffect, useCallback, FormEvent } from 'react'
import { Send, RotateCcw, ArrowRight, ArrowLeft, FileText, AlertTriangle } from 'lucide-react'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { linkify } from '@/app/components/chat/linkify'
import ReportFeedback from '@/app/components/chat/ReportFeedback'
import { EDUCATION_LEVELS, POSITIONS } from '@/app/career-path/gap'

interface IntakeOption {
  value: string
  label: string
  /** Shown with a warning but can't be selected; reason explains why. */
  disabled?: boolean
  reason?: string
  /** Multi-select: selected at first. Without any, every option starts selected. */
  preselect?: boolean
}

interface IntakeStep {
  key: string
  question: string
  subtitle: string
  options?: (string | IntakeOption)[]
  multiSelect?: boolean
  /** Most options a multi-select step accepts. */
  maxSelect?: number
  placeholder: string
}

function optionValue(opt: string | IntakeOption): string {
  return typeof opt === 'string' ? opt : opt.value
}

function optionLabel(opt: string | IntakeOption): string {
  return typeof opt === 'string' ? opt : opt.label
}

const PATH_TYPE_STEP: IntakeStep = {
  key: 'path_type',
  question: "Which of these best describes you?",
  subtitle: "This helps me give you the right information.",
  options: [
    { value: 'path1', label: "I'm deciding between college, a trade, or working right away" },
    { value: 'path2', label: "I've decided on college, comparing schools" },
    { value: 'path3', label: "I've decided on a school, comparing programs" },
    { value: 'path4', label: "I want to compare a few different career paths" },
    { value: 'path5', label: "I have a career in mind and need to know how to get there" },
  ],
  placeholder: "",
}

// Path 1: College vs vocational vs working
const DATA_SOURCE_STEP: IntakeStep = {
  key: 'data_source',
  question: "Do you have specific numbers to work with, or should I use national medians?",
  subtitle: "If you have tuition quotes or salary offers, I can use those instead of medians.",
  options: [
    { value: 'specific', label: "I have specific info (tuition quotes, salary offers, etc.)" },
    { value: 'medians', label: "Use national medians" },
  ],
  placeholder: "",
}

const SPECIFIC_NUMBERS_STEP: IntakeStep = {
  key: 'specific_numbers',
  question: "What numbers do you have?",
  subtitle: "Share any tuition quotes, salary offers, or cost estimates you've gathered.",
  placeholder: "e.g. tuition: $15,000/yr, starting salary offer: $55,000...",
}

const OCCUPATION_STEP: IntakeStep = {
  key: 'occupation',
  question: "What occupation are you interested in?",
  subtitle: "I'll compare this career path against common benchmarks.",
  placeholder: "e.g. pharmacist, software developer, nurse...",
}

// Path 2: Comparing schools
const HAS_SPECIFIC_SCHOOLS_STEP: IntakeStep = {
  key: 'has_specific_schools',
  question: "Do you have specific schools in mind?",
  subtitle: "I can compare up to 5 schools side by side.",
  options: [
    { value: 'yes', label: "Yes, I have schools I want to compare" },
    { value: 'no', label: "No, help me find schools" },
  ],
  placeholder: "",
}

const TARGET_SCHOOLS_STEP: IntakeStep = {
  key: 'target_schools',
  question: "Which schools are you considering?",
  subtitle: "I'll pull up tuition, graduation rates, debt, and earnings for each one.",
  placeholder: "e.g. University of Florida, Georgia Tech, NYU (up to 5)...",
}

const TARGET_LOCATION_STEP: IntakeStep = {
  key: 'target_location',
  question: "What state(s) or city/cities are you looking at?",
  subtitle: "I'll find top schools in those areas. Enter at least one.",
  placeholder: "e.g. Florida, California, New York...",
}

const COMPARE_METRICS_STEP: IntakeStep = {
  key: 'compare_metrics',
  question: "What do you want to compare?",
  subtitle: "All selected by default. Deselect any you don't need.",
  options: [
    "Earnings after graduation",
    "Graduation rate",
    "Net price / cost",
    "Debt at graduation",
    "Admission rate",
    "Retention rate",
    "Loan repayment rate",
  ],
  multiSelect: true,
  placeholder: "",
}

// Path 3: Comparing programs at a school
const SCHOOL_NAME_STEP: IntakeStep = {
  key: 'school_name',
  question: "What school are you at or committed to?",
  subtitle: "I'll pull program-level earnings and career data for this school.",
  placeholder: "e.g. University of Florida, MIT, Georgia Tech...",
}

const SCHOOL_SITUATION_STEP: IntakeStep = {
  key: 'school_situation',
  question: "What's your situation?",
  subtitle: "This shapes what data I focus on.",
  options: [
    { value: 'deciding', label: "Deciding between programs" },
    { value: 'current', label: "Already in a program, want to see where it leads" },
    { value: 'switching', label: "Thinking about switching programs" },
  ],
  placeholder: "",
}

const PROGRAMS_STEP: IntakeStep = {
  key: 'programs',
  question: "What program(s) are you considering or currently in?",
  subtitle: "List as many as you'd like, or say 'not sure' to see top programs.",
  placeholder: "e.g. computer science, biology, business...",
}

const SWITCH_REASON_STEP: IntakeStep = {
  key: 'switch_reason',
  question: "What's driving the change?",
  subtitle: "This helps me suggest the right alternatives.",
  options: [
    "Not enjoying it",
    "Worried about job prospects",
    "Want higher earning potential",
    "Considering dropping out",
  ],
  placeholder: "",
}

const PROGRAM_PRIORITY_STEP: IntakeStep = {
  key: 'program_priority',
  question: "What matters most?",
  subtitle: "I'll weight the analysis toward this.",
  options: [
    "Earning potential",
    "Many career options",
    "Job demand",
  ],
  placeholder: "",
}

// Path 4: Compare career tracks
const CAREERS_TO_COMPARE_STEP: IntakeStep = {
  key: 'careers_to_compare',
  question: "What careers or fields do you want to compare?",
  subtitle: "List two or more, separated by commas.",
  placeholder: "e.g. pharmacist, software developer, nurse practitioner...",
}

// Path 5: Path to a specific career
const TARGET_CAREER_STEP: IntakeStep = {
  key: 'target_career',
  question: "What career are you interested in?",
  subtitle: "I'll map out the full path to get there.",
  placeholder: "e.g. pharmacist, data scientist, electrician...",
}

const CURRENT_POSITION_STEP: IntakeStep = {
  key: 'current_position',
  question: "Where are you now?",
  subtitle: "This determines how far you need to go.",
  options: POSITIONS,
  placeholder: "",
}

const EDUCATION_LEVEL_STEP: IntakeStep = {
  key: 'education_level',
  question: "What's your highest level of education?",
  subtitle: "I'll credit the school you've already done.",
  options: EDUCATION_LEVELS.map(({ value, label }) => ({ value, label })),
  placeholder: "",
}

const CURRENT_ROLE_STEP: IntakeStep = {
  key: 'current_role',
  question: "What do you do?",
  subtitle: "I'll compare your current role to your target.",
  placeholder: "e.g. retail manager, medical assistant, IT support...",
}

function pastSchool(answers: Record<string, string>): boolean {
  return answers.current_position === 'working' || answers.current_position === 'looking_for_work'
}

function getCurrentFieldStep(answers: Record<string, string>): IntakeStep | null {
  if (answers.current_position === 'in_college') {
    return {
      key: 'current_field',
      question: "What are you studying?",
      subtitle: "I'll factor in your current progress.",
      placeholder: "e.g. biology, computer science, undeclared...",
    }
  }
  if (!pastSchool(answers)) return null
  const level = answers.education_level
  if (!EDUCATION_LEVELS.find((l) => l.value === level)?.hasField) return null
  return {
    key: 'current_field',
    question:
      level === 'some_college'
        ? "What did you study?"
        : level === 'certificate'
          ? "What's your certificate in?"
          : "What's your degree in?",
    subtitle: "I'll see how far along you already are.",
    placeholder: "e.g. psychology, business, nursing...",
  }
}

// Path 4, working users: compare against the current job, or only the named careers to each other.
const COMPARE_TO_CURRENT_STEP: IntakeStep = {
  key: 'compare_to_current',
  question: "Should I include your current job in the comparison?",
  subtitle: "Or just compare these careers to each other.",
  options: [
    { value: 'yes', label: "Yes, compare them against my current job" },
    { value: 'no', label: "No, just compare these careers to each other" },
  ],
  placeholder: "",
}

const PAYOFF_BASELINE_STEP: IntakeStep = {
  key: 'payoff_baseline',
  question: "What should the payoff be measured against?",
  subtitle: "Payoff counts the pay you give up while in school and how much more you earn after.",
  options: [
    { value: 'hs', label: "A high school diploma (national median)" },
    { value: 'salary', label: "My current salary" },
  ],
  placeholder: "",
}

const CURRENT_SALARY_STEP: IntakeStep = {
  key: 'current_salary',
  question: "What's your yearly salary?",
  subtitle: "Used only to measure the payoff, not shown as a career in the comparison.",
  placeholder: "e.g. $55,000",
}

/** Starting-point questions shared by path4 and path5, in order. */
function getStartingPointStep(answers: Record<string, string>): IntakeStep | null {
  const keys = Object.keys(answers)
  if (!keys.includes('current_position')) return CURRENT_POSITION_STEP
  if (pastSchool(answers) && !keys.includes('education_level')) return EDUCATION_LEVEL_STEP
  const fieldStep = getCurrentFieldStep(answers)
  if (fieldStep && !keys.includes('current_field')) return fieldStep
  if (answers.current_position !== 'working') return null
  if (getPathKey(answers) === 'path4') {
    if (!keys.includes('compare_to_current')) return COMPARE_TO_CURRENT_STEP
    if (answers.compare_to_current === 'no') {
      if (!keys.includes('payoff_baseline')) return PAYOFF_BASELINE_STEP
      if (answers.payoff_baseline === 'salary' && !keys.includes('current_salary')) return CURRENT_SALARY_STEP
      return null
    }
  }
  if (!keys.includes('current_role')) return CURRENT_ROLE_STEP
  return null
}

function countStartingPointSteps(answers: Record<string, string>): number {
  const pos = answers.current_position
  if (!pos) return 3
  if (pos === 'in_college') return 2
  if (pos !== 'working' && pos !== 'looking_for_work') return 1
  const level = answers.education_level
  const hasField = !level || !!EDUCATION_LEVELS.find((l) => l.value === level)?.hasField
  const comparesToCurrent = getPathKey(answers) === 'path4' && pos === 'working' ? 1 : 0
  return 2 + (hasField ? 1 : 0) + (pos === 'working' ? 1 : 0) + comparesToCurrent
}

function getRankByStep(answers: Record<string, string>): IntakeStep {
  const metrics = (answers.compare_metrics ?? '').split('|').filter(Boolean)
  return {
    key: 'rank_by',
    question: "Rank schools by which of those?",
    subtitle: "Schools will be sorted by this metric first.",
    options: metrics,
    placeholder: "",
  }
}

/** Schools the check on target_schools found for what the user typed. */
function schoolCandidates(answers: Record<string, string>): (IntakeOption & { name: string })[] {
  try {
    return JSON.parse(answers.school_candidates ?? '[]')
  } catch {
    return []
  }
}

function getSchoolPicksStep(answers: Record<string, string>): IntakeStep {
  return {
    key: 'school_picks',
    question: 'Which schools do you mean?',
    subtitle: "These match what you typed. Select the ones you mean (up to 5).",
    options: schoolCandidates(answers).map(({ value, label, disabled, reason, preselect }) => ({ value, label, disabled, reason, preselect })),
    multiSelect: true,
    maxSelect: 5,
    placeholder: '',
  }
}

/** Names of the schools the user kept, else what they typed. */
function pickedSchoolNames(answers: Record<string, string>): string | undefined {
  const picks = (answers.school_picks ?? '').split('|').filter(Boolean)
  const names = schoolCandidates(answers).filter((c) => picks.includes(c.value)).map((c) => c.name)
  return names.length > 0 ? names.join(', ') : answers.target_schools
}

/** An option that can't be picked: muted, with a warning icon and a tooltip saying why. */
function DisabledOption({ label, reason }: { label: string; reason: string }) {
  const [open, setOpen] = useState(false)
  return (
    <TooltipProvider>
      <Tooltip open={open} onOpenChange={setOpen}>
        <TooltipTrigger asChild>
          <span
            role="button"
            aria-disabled="true"
            tabIndex={0}
            onClick={() => setOpen(!open)}
            className="inline-flex cursor-help items-center gap-1.5 rounded-full border-2 border-dashed border-border px-4 py-2 text-sm text-muted-foreground"
          >
            <AlertTriangle className="h-4 w-4 text-amber-500" />
            {label}
          </span>
        </TooltipTrigger>
        <TooltipContent sideOffset={5} className="max-w-sm">
          {reason}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}

function getPathKey(answers: Record<string, string>): string {
  return answers.path_type ?? ''
}

function getNextStep(answers: Record<string, string>): IntakeStep | null {
  const keys = Object.keys(answers)

  if (!keys.includes('path_type')) return PATH_TYPE_STEP

  const path = getPathKey(answers)

  if (path === 'path1') {
    if (!keys.includes('data_source')) return DATA_SOURCE_STEP
    if (answers.data_source === 'specific' && !keys.includes('specific_numbers')) return SPECIFIC_NUMBERS_STEP
    if (!keys.includes('occupation')) return OCCUPATION_STEP
    return null
  }

  if (path === 'path2') {
    if (!keys.includes('has_specific_schools')) return HAS_SPECIFIC_SCHOOLS_STEP
    const hasSchools = answers.has_specific_schools === 'yes'
    if (hasSchools && !keys.includes('target_schools')) return TARGET_SCHOOLS_STEP
    if (hasSchools && !keys.includes('school_picks')) return getSchoolPicksStep(answers)
    if (!hasSchools && !keys.includes('target_location')) return TARGET_LOCATION_STEP
    if (!keys.includes('compare_metrics')) return COMPARE_METRICS_STEP
    const metrics = (answers.compare_metrics ?? '').split('|').filter(Boolean)
    if (metrics.length > 1 && !keys.includes('rank_by')) return getRankByStep(answers)
    return null
  }

  if (path === 'path3') {
    if (!keys.includes('school_name')) return SCHOOL_NAME_STEP
    if (!keys.includes('school_situation')) return SCHOOL_SITUATION_STEP
    if (!keys.includes('programs')) return PROGRAMS_STEP
    const switching = answers.school_situation === 'switching'
    if (switching && !keys.includes('switch_reason')) return SWITCH_REASON_STEP
    if (!keys.includes('program_priority')) return PROGRAM_PRIORITY_STEP
    return null
  }

  if (path === 'path4') {
    if (!keys.includes('careers_to_compare')) return CAREERS_TO_COMPARE_STEP
    return getStartingPointStep(answers)
  }

  if (path === 'path5') {
    if (!keys.includes('target_career')) return TARGET_CAREER_STEP
    return getStartingPointStep(answers)
  }

  return null
}

function estimateTotalSteps(answers: Record<string, string>): number {
  const path = getPathKey(answers)
  if (path === 'path1') {
    return answers.data_source === 'specific' ? 4 : 3
  }
  if (path === 'path2') {
    const metrics = (answers.compare_metrics ?? '').split('|').filter(Boolean)
    const picks = answers.has_specific_schools === 'yes' ? 1 : 0
    return (metrics.length > 1 ? 5 : 4) + picks
  }
  if (path === 'path3') {
    return answers.school_situation === 'switching' ? 6 : 5
  }
  if (path === 'path4' || path === 'path5') {
    return 2 + countStartingPointSteps(answers)
  }
  return 5
}

/** Response from /api/validate-intake (api/intake_validation.py). */
interface IntakeChoice {
  label: string
  set?: Record<string, string>
  clear?: string[]
  revalidate?: boolean
  edit?: boolean
}

interface IntakeCheck {
  status: 'ok' | 'confirm' | 'fix'
  message?: string
  set?: Record<string, string>
  choices?: IntakeChoice[]
}

/** Answers derived from a step by its check; dropped when the user goes back past that step. */
const DERIVED_KEYS: Record<string, string[]> = {
  occupation: ['occupation_code', 'occupation_title'],
  target_schools: ['school_candidates'],
  specific_numbers: ['user_numbers'],
  current_salary: ['current_salary_value'],
}
const HIDDEN_KEYS = new Set(Object.values(DERIVED_KEYS).flat())

async function checkIntakeAnswer(key: string, value: string, answers: Record<string, string>): Promise<IntakeCheck> {
  try {
    const res = await fetch('/api/validate-intake', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key, value, answers }),
    })
    if (!res.ok) return { status: 'ok' }
    return (await res.json()) as IntakeCheck
  } catch {
    // Never block the intake on a failed check; the report step handles raw answers.
    return { status: 'ok' }
  }
}

function IntakeFlow({ onComplete }: { onComplete: (answers: Record<string, string>) => void }) {
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [history, setHistory] = useState<string[]>([])
  // Last value entered for each step, so going back doesn't make the user retype it.
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const [selected, setSelected] = useState('')
  const [selections, setSelections] = useState<string[]>([])
  const [input, setInput] = useState('')
  const [checking, setChecking] = useState(false)
  const [check, setCheck] = useState<IntakeCheck | null>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  const current = getNextStep(answers)
  const answeredCount = Object.keys(answers).filter((k) => !HIDDEN_KEYS.has(k)).length
  const totalEstimate = estimateTotalSteps(answers)
  const progress = current ? (answeredCount / totalEstimate) * 100 : 100

  useEffect(() => {
    inputRef.current?.focus()
  }, [answeredCount])

  useEffect(() => {
    if (!current) return
    setCheck(null)
    const saved = answers[current.key] ?? drafts[current.key] ?? ''
    if (current.multiSelect) {
      const options = (current.options ?? []).filter((o) => typeof o === 'string' || !o.disabled)
      const preselected = options.filter((o) => typeof o !== 'string' && o.preselect)
      const initial = options.some((o) => typeof o !== 'string' && o.preselect !== undefined) ? preselected : options
      setSelections(saved ? saved.split('|') : initial.map(optionValue))
      setSelected('')
    } else {
      setSelected(saved)
      setSelections([])
    }
    setInput(saved)
  }, [current?.key])

  // Multi-select answers keep the options' order, not click order, so later
  // steps (e.g. rank by) list them the same way.
  const pending = current?.multiSelect
    ? (current.options ?? []).map(optionValue).filter((v) => selections.includes(v)).join('|')
    : current?.options
      ? selected
      : input.trim()

  const tooMany = !!current?.maxSelect && selections.length > current.maxSelect

  /** Saves the step's answer (plus anything its check set or cleared) and moves on. */
  function finish(next: Record<string, string>, clear: string[] = []) {
    if (!current) return
    for (const key of clear) delete next[key]
    const added = Object.keys(next).filter((k) => !(k in answers) && k !== current.key && !HIDDEN_KEYS.has(k))
    setHistory((prev) => [
      ...prev.filter((k) => !clear.includes(k)),
      ...(clear.includes(current.key) ? [] : [current.key]),
      ...added,
    ])
    setDrafts((prev) => ({ ...prev, [current.key]: pending, ...next }))
    setAnswers(next)
    setCheck(null)
    setSelected('')
    setSelections([])
    setInput('')
    if (!getNextStep(next)) {
      onComplete(next)
    }
  }

  async function runCheck(value: string, base: Record<string, string>) {
    if (!current) return
    setChecking(true)
    const result = await checkIntakeAnswer(current.key, value, base)
    setChecking(false)
    if (result.status === 'ok') finish({ ...base, [current.key]: value, ...(result.set ?? {}) })
    else setCheck(result)
  }

  function advance() {
    if (!pending || !current || checking || tooMany) return
    // Free-text answers get checked (one occupation, usable numbers, ...) before moving on.
    if (!current.options) {
      runCheck(pending, answers)
      return
    }
    finish({ ...answers, [current.key]: pending })
  }

  function choose(choice: IntakeChoice) {
    if (!current) return
    if (choice.edit) {
      setCheck(null)
      inputRef.current?.focus()
      return
    }
    const next = { ...answers, [current.key]: pending, ...(choice.set ?? {}) }
    if (choice.revalidate) {
      // The choice replaced this step's answer (e.g. picked one of several occupations).
      const value = choice.set?.[current.key] ?? pending
      setInput(value)
      setCheck(null)
      runCheck(value, answers)
      return
    }
    finish(next, choice.clear)
  }

  function goBack() {
    if (history.length === 0) return
    const lastKey = history[history.length - 1]
    setHistory((prev) => prev.slice(0, -1))
    setAnswers((prev) => {
      const next = { ...prev }
      delete next[lastKey]
      for (const key of DERIVED_KEYS[lastKey] ?? []) delete next[key]
      return next
    })
    setCheck(null)
    setSelected('')
    setSelections([])
    setInput('')
  }

  function toggleSelection(option: string) {
    setSelections((prev) =>
      prev.includes(option)
        ? prev.filter((s) => s !== option)
        : [...prev, option]
    )
  }

  if (!current) return null

  return (
    <div className="flex min-h-screen flex-col">
      <div className="border-b px-4 py-3">
        <div className="mx-auto flex max-w-2xl items-center justify-between">
          <Link href="/" className="text-muted-foreground hover:text-foreground transition-colors">
            <ArrowLeft className="h-5 w-5" />
          </Link>
          <span className="text-sm font-medium text-foreground">Counselor Agent</span>
          <div className="w-5" />
        </div>
        <div className="mx-auto mt-3 max-w-2xl">
          <div className="h-1 w-full rounded-full bg-secondary">
            <div
              className="h-1 rounded-full bg-primary transition-all duration-500"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      </div>

      <div className="flex flex-1 flex-col items-center justify-center px-4">
        <div className="w-full max-w-2xl space-y-8">
          <div className="text-center space-y-2">
            <h1 className="text-3xl sm:text-4xl font-bold tracking-tight">
              {current.question}
            </h1>
            <p className="text-muted-foreground text-lg">
              {current.subtitle}
            </p>
          </div>

          {current.options && (
            <div className="flex flex-wrap justify-center gap-2">
              {current.options.map((option) => {
                const value = optionValue(option)
                const label = optionLabel(option)
                if (typeof option !== 'string' && option.disabled) {
                  return <DisabledOption key={value} label={label} reason={option.reason ?? ''} />
                }
                const isSelected = current.multiSelect
                  ? selections.includes(value)
                  : selected === value
                return (
                  <button
                    key={value}
                    onClick={() => {
                      if (current.multiSelect) {
                        toggleSelection(value)
                      } else {
                        setSelected(selected === value ? '' : value)
                      }
                    }}
                    className={cn(
                      'rounded-full border-2 px-4 py-2 text-sm transition-all',
                      isSelected
                        ? 'border-primary bg-primary/10 text-primary'
                        : 'border-border hover:border-primary hover:bg-primary/5'
                    )}
                  >
                    {label}
                  </button>
                )
              })}
            </div>
          )}

          {current.placeholder && (
            <div className="relative">
              <textarea
                ref={inputRef}
                value={input}
                onChange={(e) => {
                  setInput(e.target.value)
                  setSelected('')
                  setSelections([])
                  e.target.style.height = 'auto'
                  e.target.style.height = `${Math.min(e.target.scrollHeight, 160)}px`
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    advance()
                  }
                }}
                placeholder={current.placeholder}
                rows={3}
                className="w-full resize-none rounded-xl border border-input bg-background px-4 py-3 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              />
            </div>
          )}

          {check && check.status !== 'ok' && (
            <div role="status" className="space-y-3 rounded-xl border border-primary/40 bg-primary/5 px-4 py-3">
              {check.message && <p className="text-sm">{check.message}</p>}
              {check.choices && check.choices.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {check.choices.map((choice) => (
                    <button
                      key={choice.label}
                      onClick={() => choose(choice)}
                      disabled={checking}
                      className="rounded-full border-2 border-border px-4 py-2 text-sm transition-all hover:border-primary hover:bg-primary/5 disabled:opacity-50"
                    >
                      {choice.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      <div className="border-t px-4 py-4">
        <div className="mx-auto flex max-w-2xl items-center justify-center gap-3">
          <Button
            variant="outline"
            onClick={goBack}
            disabled={history.length === 0}
            className="gap-1.5"
          >
            <ArrowLeft className="h-4 w-4" />
            Back
          </Button>
          <Button
            onClick={advance}
            disabled={!pending || checking || tooMany}
            className="gap-1.5"
          >
            {checking ? 'Checking…' : 'Next'}
            <ArrowRight className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  )
}

interface Message {
  role: 'user' | 'assistant'
  content: string
  report_html?: string
  report_status?: 'success' | 'failed' | 'skipped'
  report_viewed?: boolean
  error?: boolean
}

interface Progress {
  message: string
  percent?: number
}

function ProgressIndicator({ progress }: { progress: Progress | null }) {
  return (
    <div className="w-full max-w-sm space-y-2 rounded-lg bg-secondary px-4 py-3 text-sm text-muted-foreground">
      {progress?.message && <div>{progress.message}</div>}
      {typeof progress?.percent === 'number' && (
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
          <div
            className="h-full rounded-full bg-primary transition-all duration-500"
            style={{ width: `${progress.percent}%` }}
          />
        </div>
      )}
    </div>
  )
}

function ChatView({ initialPrompt, intakeAnswers }: { initialPrompt: string; intakeAnswers: Record<string, string> }) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [progress, setProgress] = useState<Progress | null>(null)
  const [retryingIndex, setRetryingIndex] = useState<number | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const conversationHistoryRef = useRef<Record<string, unknown>[]>([])
  const sentInitial = useRef(false)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, progress])

  useEffect(() => {
    if (sentInitial.current) return
    sentInitial.current = true
    sendMessage(initialPrompt)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleNewConversation = useCallback(() => {
    setMessages([])
    conversationHistoryRef.current = []
    window.location.reload()
  }, [])

  function openReport(messageIndex: number, html: string) {
    setMessages((prev) => prev.map((m, i) => (i === messageIndex ? { ...m, report_viewed: true } : m)))
    const blob = new Blob([html], { type: 'text/html' })
    const url = URL.createObjectURL(blob)
    window.open(url, '_blank')
  }

  async function retryReport(messageIndex: number) {
    const msg = messages[messageIndex]
    setRetryingIndex(messageIndex)

    try {
      const res = await fetch('/api/retry-report', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          intake_answers: intakeAnswers,
          conversation_history: conversationHistoryRef.current,
          agent_text: msg.content,
        }),
      })

      if (!res.ok) throw new Error(`Server error: ${res.status}`)

      const report = await res.json()

      if (report.html) {
        setMessages((prev) => prev.map((m, i) =>
          i === messageIndex
            ? { ...m, content: report.summary || m.content, report_html: report.html, report_status: 'success' as const }
            : m
        ))
      } else {
        console.error('Report retry returned empty HTML:', report.error)
        setMessages((prev) => prev.map((m, i) =>
          i === messageIndex ? { ...m, report_status: 'failed' as const } : m
        ))
      }
    } catch (err) {
      console.error('Report retry failed:', err)
      setMessages((prev) => prev.map((m, i) =>
        i === messageIndex ? { ...m, report_status: 'failed' as const } : m
      ))
    } finally {
      setRetryingIndex(null)
    }
  }

  async function sendMessage(text: string) {
    setMessages((prev) => [...prev, { role: 'user', content: text }])
    setLoading(true)
    setProgress({ message: 'Connecting…' })

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text,
          conversation_history: conversationHistoryRef.current,
          intake_answers: intakeAnswers,
        }),
      })

      if (!res.ok) throw new Error(`Server error: ${res.status}`)

      const reader = res.body?.getReader()
      if (!reader) throw new Error('No response stream')

      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n\n')
        buffer = lines.pop() ?? ''

        for (const line of lines) {
          const dataLine = line.trim()
          if (!dataLine.startsWith('data: ')) continue
          const event = JSON.parse(dataLine.slice(6))

          if (event.event === 'progress') {
            setProgress({ message: event.message, percent: event.percent })
          } else if (event.event === 'complete') {
            console.log('Agent complete:', {
              report_status: event.report_status,
              report_html_length: event.report_html?.length ?? 0,
            })
            conversationHistoryRef.current = event.conversation_history
            setMessages((prev) => [
              ...prev,
              {
                role: 'assistant' as const,
                content: event.response,
                report_html: event.report_html || undefined,
                report_status: event.report_status,
              },
            ])
          }
        }
      }
    } catch (err) {
      console.error('Agent request failed:', err)
      setMessages((prev) => [
        ...prev,
        { role: 'assistant' as const, content: 'Something went wrong.', error: true },
      ])
    } finally {
      setLoading(false)
      setProgress(null)
      inputRef.current?.focus()
    }
  }

  function retry() {
    const lastUserIndex = messages.findLastIndex((m) => m.role === 'user')
    if (lastUserIndex === -1) return
    const text = messages[lastUserIndex].content
    setMessages((prev) => prev.filter((m) => !m.error).slice(0, lastUserIndex))
    sendMessage(text)
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const text = input.trim()
    if (!text || loading) return
    setInput('')
    if (inputRef.current) inputRef.current.style.height = 'auto'
    sendMessage(text)
  }

  return (
    <div className="flex h-screen flex-col">
      <div className="flex items-center justify-between border-b px-4 py-3">
        <div className="flex items-center gap-3">
          <Link href="/" className="text-muted-foreground hover:text-foreground transition-colors">
            <ArrowLeft className="h-5 w-5" />
          </Link>
          <div>
            <h1 className="text-sm font-semibold">Counselor Agent</h1>
            <p className="text-xs text-muted-foreground">
              Personalized guidance for your situation
            </p>
          </div>
        </div>
        <Button
          variant="ghost"
          size="icon"
          onClick={handleNewConversation}
          title="Start over"
        >
          <RotateCcw className="h-4 w-4" />
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4">
        <div className="mx-auto max-w-2xl space-y-3">
          {messages.map((msg, i) => (
            <div key={i} className="space-y-2">
              <div
                className={cn(
                  'flex',
                  msg.role === 'user' ? 'justify-end' : 'justify-start'
                )}
              >
                <div
                  className={cn(
                    'max-w-[85%] rounded-lg px-3 py-2 text-sm whitespace-pre-wrap',
                    msg.role === 'user'
                      ? 'bg-primary text-primary-foreground'
                      : msg.error
                        ? 'bg-destructive/10 text-destructive'
                        : 'bg-secondary text-secondary-foreground'
                  )}
                >
                  {msg.role === 'assistant' ? linkify(msg.content) : msg.content}
                  {msg.error && (
                    <button
                      onClick={retry}
                      disabled={loading}
                      className="mt-2 flex items-center gap-1.5 text-xs font-medium text-destructive hover:underline disabled:opacity-50"
                    >
                      <RotateCcw className="h-3 w-3" />
                      Retry
                    </button>
                  )}
                </div>
              </div>

              {msg.report_html && (
                <div className="flex justify-start">
                  <button
                    onClick={() => openReport(i, msg.report_html!)}
                    className="flex items-center gap-2 rounded-lg border border-primary/30 bg-primary/5 px-4 py-2.5 text-sm font-medium text-primary transition-colors hover:bg-primary/10"
                  >
                    <FileText className="h-4 w-4" />
                    View report
                  </button>
                </div>
              )}

              {msg.report_html && msg.report_viewed && (
                <ReportFeedback
                  question={messages.slice(0, i).findLast((m) => m.role === 'user')?.content ?? ''}
                  summary={msg.content}
                  intakeAnswers={intakeAnswers}
                />
              )}

              {msg.report_status === 'failed' && !msg.report_html && (
                <div className="flex justify-start">
                  <button
                    onClick={() => retryReport(i)}
                    disabled={retryingIndex === i}
                    className="flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-50 px-4 py-2.5 text-sm font-medium text-amber-700 transition-colors hover:bg-amber-100 disabled:opacity-50 dark:bg-amber-950/30 dark:text-amber-400 dark:hover:bg-amber-950/50"
                  >
                    <RotateCcw className={cn('h-4 w-4', retryingIndex === i && 'animate-spin')} />
                    {retryingIndex === i ? 'Generating report…' : 'Generate report'}
                  </button>
                </div>
              )}
            </div>
          ))}

          {loading && (
            <div className="flex justify-start">
              <ProgressIndicator progress={progress} />
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </div>

      <form onSubmit={handleSubmit} className="border-t px-4 py-3">
        <div className="mx-auto flex max-w-2xl items-end gap-2">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => {
              setInput(e.target.value)
              e.target.style.height = 'auto'
              e.target.style.height = `${Math.min(e.target.scrollHeight, 120)}px`
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                handleSubmit(e)
              }
            }}
            placeholder="Ask a follow-up question..."
            disabled={loading}
            rows={1}
            className="flex min-h-9 max-h-[120px] flex-1 resize-none rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
          />
          <Button
            type="submit"
            size="icon"
            className="h-9 w-9 shrink-0"
            disabled={loading || !input.trim()}
          >
            <Send className="h-4 w-4" />
          </Button>
        </div>
      </form>
    </div>
  )
}

const PATH_LABELS: Record<string, string> = {
  path1: 'College vs Vocational vs Working Now',
  path2: 'Comparing Schools',
  path3: 'Comparing Programs at a School',
  path4: 'Compare Career Tracks',
  path5: 'Path to a Specific Career',
}

const METRIC_TO_SORT: Record<string, string> = {
  'Earnings after graduation': 'earnings',
  'Graduation rate': 'graduation_rate',
  'Net price / cost': 'net_price',
  'Debt at graduation': 'median_debt',
  'Admission rate': 'admission_rate',
  'Retention rate': 'retention_rate',
  'Loan repayment rate': 'loan_repayment',
}

function startingPointLines(answers: Record<string, string>): string[] {
  const lines: string[] = []
  const position = POSITIONS.find((p) => p.value === answers.current_position)
  if (position) lines.push(`- Current position: ${position.label}`)
  const level = EDUCATION_LEVELS.find((l) => l.value === answers.education_level)
  if (level) lines.push(`- Highest education: ${level.label}`)
  if (answers.current_field) lines.push(`- Field of study: ${answers.current_field}`)
  if (answers.current_role) lines.push(`- Current job: ${answers.current_role}`)
  if (answers.compare_to_current === 'no') {
    lines.push('- Compare only these careers to each other, not to my current job')
    if (answers.payoff_baseline === 'salary' && answers.current_salary_value) {
      lines.push(`- Measure payoff against my current salary of $${Number(answers.current_salary_value).toLocaleString()}`)
    } else {
      lines.push('- Measure payoff against a high school diploma (national median)')
    }
  }
  return lines
}

function buildPrompt(answers: Record<string, string>): string {
  const path = getPathKey(answers)
  const pathLabel = PATH_LABELS[path] ?? 'General'
  const lines = [`Decision point: ${pathLabel}`, '', "Here's my situation:"]

  if (path === 'path1') {
    lines.push(`- I'm deciding between college, a trade, or working right away`)
    if (answers.data_source === 'specific') {
      lines.push('- Data preference: has specific numbers (tuition quotes, salary offers)')
    } else if (answers.data_source === 'medians') {
      lines.push('- Data preference: use national medians')
    }
    if (answers.specific_numbers) lines.push(`- My specific numbers: ${answers.specific_numbers}`)
    if (answers.occupation) lines.push(`- Occupation I'm interested in: ${answers.occupation_title ?? answers.occupation}`)
    lines.push('')
    lines.push('Compare these five options side by side: (1) HS diploma baseline, (2) Cashier, (3) Electrician, (4) Bachelor\'s degree median, (5) my chosen occupation. Include full financial analysis with payoff timeline.')
  }

  if (path === 'path2') {
    lines.push(`- I've decided on college, comparing schools`)
    if (answers.target_schools) lines.push(`- Schools to compare: ${pickedSchoolNames(answers)}`)
    if (answers.target_location) lines.push(`- Location: ${answers.target_location}`)
    if (answers.compare_metrics) {
      const metrics = answers.compare_metrics.split('|')
      lines.push(`- Compare on: ${metrics.join(', ')}`)
    }
    const rankMetric = answers.rank_by ?? (answers.compare_metrics?.split('|').filter(Boolean).length === 1 ? answers.compare_metrics : '')
    if (rankMetric) {
      lines.push(`- Rank by: ${rankMetric}`)
      const sortKey = METRIC_TO_SORT[rankMetric]
      if (sortKey) lines.push(`- sort_by: ${sortKey}`)
    }
    lines.push('')
    lines.push('Show me up to 5 schools ranked by my chosen metric, with only the metrics I selected. Include full financial analysis.')
  }

  if (path === 'path3') {
    lines.push(`- I'm at or committed to a specific school, comparing programs`)
    if (answers.school_name) lines.push(`- School: ${answers.school_name}`)
    if (answers.school_situation) {
      const situationText: Record<string, string> = {
        deciding: 'Deciding between programs',
        current: 'Already in a program, exploring outcomes',
        switching: 'Thinking about switching programs',
      }
      lines.push(`- Situation: ${situationText[answers.school_situation] ?? answers.school_situation}`)
    }
    if (answers.programs) lines.push(`- Programs: ${answers.programs}`)
    if (answers.switch_reason) lines.push(`- Reason for switching: ${answers.switch_reason}`)
    if (answers.program_priority) lines.push(`- What matters most: ${answers.program_priority}`)
    lines.push('')
    lines.push('Compare programs at my school. Show school-specific earnings (Scorecard) and national occupation salary (BLS) for each. Include career options, demand, and bright outlook. Full financial analysis.')
  }

  if (path === 'path4') {
    lines.push(`- I want to compare career paths side by side`)
    if (answers.careers_to_compare) lines.push(`- Careers to compare: ${answers.careers_to_compare}`)
    lines.push(...startingPointLines(answers))
    lines.push('')
    lines.push('Compare each career path: education required, timeline, cost, salary, bright outlook, payoff timeline. Full financial analysis for all paths.')
  }

  if (path === 'path5') {
    lines.push(`- I have a specific career in mind`)
    if (answers.target_career) lines.push(`- Target career: ${answers.target_career}`)
    lines.push(...startingPointLines(answers))
    lines.push('')
    lines.push('Map out the full path from where I am to the target career. Steps, timeline, education, cost, expected salary, time to recoup. Show gap analysis if I have relevant education.')
  }

  return lines.join('\n')
}

export default function CounselorPage() {
  const [phase, setPhase] = useState<'intake' | 'chat'>('intake')
  const [prompt, setPrompt] = useState('')
  const [answers, setAnswers] = useState<Record<string, string>>({})

  function handleIntakeComplete(intake: Record<string, string>) {
    setAnswers(intake)
    setPrompt(buildPrompt(intake))
    setPhase('chat')
  }

  if (phase === 'intake') {
    return <IntakeFlow onComplete={handleIntakeComplete} />
  }

  return <ChatView initialPrompt={prompt} intakeAnswers={answers} />
}
