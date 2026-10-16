// Seeds School from the College Scorecard API: every operating school that
// awards a bachelor's or higher. Filtering on the highest degree, not the
// predominant one, keeps graduate-only schools (medical, law) and universities
// that mostly award certificates or associate's degrees but have bachelor's
// programs (Weber State, BYU-Idaho). Only schools with school-wide earnings
// and debt are stored here; seed-school-programs adds the ones that have only
// program data. Safe to rerun; rows are upserted.
import { PrismaClient } from '@prisma/client'
import { fetchSchoolsPage, hasSchoolData, mapSchool, upsertSchools, type SchoolRow } from '../src/lib/scorecard'

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
    const result = await fetchSchoolsPage({ minHighestDegree: BACHELOR }, page, PER_PAGE)
    total = result.total
    const rows = result.results.map(mapSchool).filter((r): r is SchoolRow => r !== null && hasSchoolData(r))
    skipped += result.results.length - rows.length
    await upsertSchools(prisma, rows)
    saved += rows.length
    console.log(`page ${page + 1}/${Math.ceil(total / PER_PAGE)}: saved ${saved}/${total}`)
    page++
    await sleep(DELAY_MS)
  }

  console.log(`Done. ${saved} schools saved, ${skipped} skipped (missing name/city/state, or no school-wide earnings and debt).`)
}

main()
  .catch((e) => {
    console.error(e)
    process.exit(1)
  })
  .finally(() => prisma.$disconnect())
