import Link from 'next/link'
import { Compass, Mountain } from 'lucide-react'

export default function LandingPage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-4 sm:p-6 md:p-16">
      <div className="w-full max-w-xl space-y-10 text-center">
        <div className="space-y-3">
          <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-balance">
            Find your next right step
          </h1>
          <p className="text-muted-foreground text-lg">
            College, trades, or a new career. How do you want to find your way?
          </p>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Link
            href="/chat"
            className="group flex flex-col items-center gap-4 rounded-xl border-2 border-border p-8 transition-all hover:border-primary hover:shadow-md"
          >
            <Mountain className="h-10 w-10 text-muted-foreground group-hover:text-primary transition-colors" />
            <div className="space-y-1">
              <span className="text-lg font-semibold">Guided experience</span>
              <p className="text-sm text-muted-foreground">
                Tell our AI counselor about your situation and get a personalized report.
              </p>
            </div>
          </Link>

          <Link
            href="/explore"
            className="group flex flex-col items-center gap-4 rounded-xl border-2 border-border p-8 transition-all hover:border-primary hover:shadow-md"
          >
            <Compass className="h-10 w-10 text-muted-foreground group-hover:text-primary transition-colors" />
            <div className="space-y-1">
              <span className="text-lg font-semibold">Explore on your own</span>
              <p className="text-sm text-muted-foreground">
                Compare schools, programs, and careers at your own pace.
              </p>
            </div>
          </Link>
        </div>
      </div>
    </main>
  )
}
