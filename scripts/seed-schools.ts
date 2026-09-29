// Seeds School from the College Scorecard API: every operating school whose
// predominant degree is a bachelor's. Safe to rerun; rows are upserted.
import { PrismaClient } from '@prisma/client'
import { fetchSchoolsPage, mapSchool, upsertSchools, type SchoolRow } from '../src/lib/scorecard'

process.loadEnvFile()

const prisma = new PrismaClient()
const PER_PAGE = 100
const BACHELOR = 3
const DELAY_MS = 500

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

async function main() {
  let page = 0
  let total = Infinity
  let saved = 0
  let skipped = 0

  while (page * PER_PAGE < total) {
    const result = await fetchSchoolsPage({ predominantDegree: BACHELOR }, page, PER_PAGE)
    total = result.total
    const rows = result.results.map(mapSchool).filter((r): r is SchoolRow => r !== null)
    skipped += result.results.length - rows.length
    await upsertSchools(prisma, rows)
    saved += rows.length
    console.log(`page ${page + 1}/${Math.ceil(total / PER_PAGE)}: saved ${saved}/${total}`)
    page++
    await sleep(DELAY_MS)
  }

  console.log(`Done. ${saved} schools saved, ${skipped} skipped (missing name/city/state).`)
}

main()
  .catch((e) => {
    console.error(e)
    process.exit(1)
  })
  .finally(() => prisma.$disconnect())
