import type { Metadata } from 'next'
import CareerPath from './CareerPath'

export const metadata: Metadata = {
  title: 'Career Path · Next Right Step',
}

export default function CareerPathPage() {
  return <CareerPath />
}
