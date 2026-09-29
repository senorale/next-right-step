import Link from 'next/link'

/** Points to the FAQ for data sources and assumptions behind the path pages. */
export default function MoreDetails() {
  return (
    <p className="text-center text-sm text-muted-foreground">
      Where do these numbers come from?{' '}
      <Link href="/faq" className="text-primary hover:underline">
        More details
      </Link>
    </p>
  )
}
