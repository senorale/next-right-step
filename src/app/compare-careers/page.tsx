import type { Metadata } from 'next'
import CompareCareers from './CompareCareers'

export const metadata: Metadata = {
  title: 'Compare Careers · Next Right Step',
}

export default function CompareCareersPage() {
  return <CompareCareers />
}
