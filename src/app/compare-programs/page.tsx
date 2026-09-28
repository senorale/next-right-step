import type { Metadata } from 'next'
import ComparePrograms from './ComparePrograms'

export const metadata: Metadata = {
  title: 'Compare Programs · Next Right Step',
}

export default function CompareProgramsPage() {
  return <ComparePrograms />
}
