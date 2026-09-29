// Fills School.predominant_degree for rows stored before the column existed.
// Additive and safe to rerun: only rows where the column is null are updated.
import { PrismaClient } from '@prisma/client'
import { fetchSchoolsPage } from '../src/lib/scorecard'

process.loadEnvFile()

const prisma = new PrismaClient()
const BATCH = 100
const DELAY_MS = 500

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

async function main() {
  const missing = await prisma.school.findMany({
    where: { predominant_degree: null },
    select: { school_id: true },
    orderBy: { school_id: 'asc' },
  })
  console.log(`${missing.length} schools missing predominant_degree`)

  let updated = 0
  for (let i = 0; i < missing.length; i += BATCH) {
    const ids = missing.slice(i, i + BATCH).map((s) => s.school_id)
    const page = await fetchSchoolsPage({ ids }, 0, BATCH)
    for (const r of page.results) {
      const id = r.id
      const degree = r['school.degrees_awarded.predominant']
      if (typeof id !== 'number' || typeof degree !== 'number') continue
      const { count } = await prisma.school.updateMany({
        where: { school_id: id, predominant_degree: null },
        data: { predominant_degree: degree },
      })
      updated += count
    }
    console.log(`batch ${i / BATCH + 1}/${Math.ceil(missing.length / BATCH)}: updated ${updated}`)
    await sleep(DELAY_MS)
  }

  console.log(`Done. ${updated} schools updated.`)
}

main()
  .catch((e) => {
    console.error(e)
    process.exit(1)
  })
  .finally(() => prisma.$disconnect())
