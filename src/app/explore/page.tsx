import type { Metadata } from 'next'
import Link from 'next/link'
import { PATHS } from '../components/paths/paths'

export const metadata: Metadata = {
  title: 'Explore paths · Next Right Step',
}

export default function ExploreHub() {
  return (
    <main className="flex min-h-screen flex-col items-center p-4 sm:p-6 md:p-16">
      <div className="w-full max-w-3xl space-y-8">
        <div className="space-y-2 text-center">
          <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">Where are you headed?</h1>
          <p className="text-lg text-muted-foreground">Pick the path that fits where you are right now.</p>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          {PATHS.map(({ href, title, who, description, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              className="group flex gap-4 rounded-xl border-2 border-border p-5 transition-all hover:border-primary hover:shadow-md"
            >
              <Icon className="h-8 w-8 shrink-0 text-muted-foreground transition-colors group-hover:text-primary" />
              <div className="space-y-1">
                <span className="font-semibold">{title}</span>
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{who}</p>
                <p className="text-sm text-muted-foreground">{description}</p>
              </div>
            </Link>
          ))}
        </div>

        <p className="text-center text-sm text-muted-foreground">
          Not sure where to start?{' '}
          <Link href="/chat" className="text-primary hover:underline">
            Try the guided experience with our AI counselor
          </Link>
          .
        </p>
      </div>
    </main>
  )
}
