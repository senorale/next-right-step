import Link from 'next/link'

export default function PathHeader({ title, description }: { title: string; description: string }) {
  return (
    <div className="space-y-2">
      <Link href="/explore" className="text-sm text-primary hover:underline">
        ← All paths
      </Link>
      <h1 className="text-3xl font-bold tracking-tight">{title}</h1>
      <p className="text-muted-foreground">{description}</p>
    </div>
  )
}
