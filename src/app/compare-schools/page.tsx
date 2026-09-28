import type { Metadata } from 'next'
import CompareSchools from './CompareSchools'

export const metadata: Metadata = {
  title: 'Compare Schools · Next Right Step',
}

export default function CompareSchoolsPage() {
  return <CompareSchools />
}
