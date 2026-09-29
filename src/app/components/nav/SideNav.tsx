'use client'

import { useState } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Compass, HelpCircle, Mountain, PanelLeftClose, PanelLeftOpen } from 'lucide-react'
import { cn } from '@/lib/utils'
import { PATHS } from '../paths/paths'

// The two experiences from the landing page, with the same icons, plus the FAQ.
// Explore stays active on its five path pages, which the /explore hub lists.
const links = [
  { href: '/chat', label: 'Guided experience', icon: Mountain, matches: ['/chat'] },
  { href: '/explore', label: 'Explore on your own', icon: Compass, matches: ['/explore', ...PATHS.map((p) => p.href)] },
  { href: '/faq', label: 'FAQ', icon: HelpCircle, matches: ['/faq'] },
]

export default function SideNav() {
  const [collapsed, setCollapsed] = useState(true)
  const pathname = usePathname()

  return (
    <aside
      className={cn(
        'sticky top-0 h-screen shrink-0 border-r bg-card transition-all duration-200',
        collapsed ? 'w-14' : 'w-56'
      )}
    >
      <div className="flex h-full flex-col gap-1 p-2">
        <button
          onClick={() => setCollapsed((c) => !c)}
          className="flex items-center justify-center rounded-md p-2 text-muted-foreground hover:bg-accent"
          aria-label={collapsed ? 'Expand navigation' : 'Collapse navigation'}
        >
          {collapsed ? (
            <PanelLeftOpen className="h-5 w-5" />
          ) : (
            <PanelLeftClose className="h-5 w-5" />
          )}
        </button>

        <nav className="mt-2 flex flex-col gap-1">
          {links.map(({ href, label, icon: Icon, matches }) => {
            const active = matches.some((m) => pathname === m || pathname.startsWith(`${m}/`))
            return (
              <Link
                key={href}
                href={href}
                title={label}
                className={cn(
                  'flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors',
                  active
                    ? 'bg-primary text-primary-foreground'
                    : 'text-foreground hover:bg-accent'
                )}
              >
                <Icon className="h-5 w-5 shrink-0" />
                {!collapsed && <span className="truncate">{label}</span>}
              </Link>
            )
          })}
        </nav>
      </div>
    </aside>
  )
}
