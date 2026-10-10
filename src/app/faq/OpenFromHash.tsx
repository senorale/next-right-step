'use client'

import { useEffect } from 'react'

/** Opens and scrolls to the FAQ entry named in the URL hash (e.g. /faq#find-your-occupation). */
export default function OpenFromHash() {
  useEffect(() => {
    const id = decodeURIComponent(window.location.hash.slice(1))
    const entry = id ? document.getElementById(id) : null
    if (entry instanceof HTMLDetailsElement) {
      entry.open = true
      entry.scrollIntoView({ block: 'start' })
    }
  }, [])
  return null
}
