import { BookOpen, Briefcase, Route, Scale, School, type LucideIcon } from 'lucide-react'

export interface PathLink {
  href: string
  title: string
  who: string
  description: string
  icon: LucideIcon
}

// The five self-exploration paths, in the same order as the chat intake.
export const PATHS: PathLink[] = [
  {
    href: '/college-vs-alternatives',
    title: 'College vs alternatives',
    who: "Not sure college is right for you",
    description: 'Compare college with trades and working right away: cost, salary, and how long each takes to pay off.',
    icon: Scale,
  },
  {
    href: '/compare-schools',
    title: 'Compare schools',
    who: "Going to college, choosing where",
    description: 'Put schools side by side on net price, graduation rate, debt, and earnings.',
    icon: School,
  },
  {
    href: '/compare-programs',
    title: 'Compare programs',
    who: 'Know your school, choosing a program',
    description: 'See what graduates of each program at your school earn and borrow.',
    icon: BookOpen,
  },
  {
    href: '/compare-careers',
    title: 'Compare careers',
    who: 'Weighing a few career options',
    description: 'Compare salaries, education cost, and payoff from where you are today.',
    icon: Briefcase,
  },
  {
    href: '/career-path',
    title: 'Path to a career',
    who: 'Know the career you want',
    description: 'Map the education you still need, what it costs, and how long until it pays off.',
    icon: Route,
  },
]
