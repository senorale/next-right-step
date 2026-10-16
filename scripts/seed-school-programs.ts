// Seeds SchoolProgram from the College Scorecard API: every program with
// earnings (1 or 4 years after graduating) at schools awarding a bachelor's or
// higher, with its median debt. A school with such programs is stored with
// them, so schools seed-schools skipped for lacking school-wide data still
// come in for their programs. Programs without earnings aren't stored. Safe to
// rerun; rows are upserted, so a rerun picks up Scorecard's latest figures.
import { PrismaClient } from '@prisma/client'
import {
  fetchSchoolsWithProgramsPage,
  mapPrograms,
  mapSchool,
  upsertPrograms,
  upsertSchools,
  type ScorecardPage,
  type SchoolProgramRow,
  type SchoolRow,
} from '../src/lib/scorecard'

process.loadEnvFile()

const prisma = new PrismaClient()
const PER_PAGE = 50
const BACHELOR = 3
const DELAY_MS = 500
const RETRIES = 4

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

/** Scorecard drops connections now and then on big pages. */
async function fetchWithRetry(page: number): Promise<ScorecardPage> {
  for (let attempt = 0; ; attempt++) {
    try {
      return await fetchSchoolsWithProgramsPage({ minHighestDegree: BACHELOR }, page, PER_PAGE)
    } catch (e) {
      if (attempt === RETRIES) throw e
      console.log(`page ${page + 1} failed (${e}), retrying`)
      await sleep(5000 * (attempt + 1))
    }
  }
}

async function main() {
  let page = 0
  let total = Infinity
  let schools = 0
  let programs = 0

  while (page * PER_PAGE < total) {
    const result = await fetchWithRetry(page)
    total = result.total
    const pageSchools: SchoolRow[] = []
    const pagePrograms: SchoolProgramRow[] = []
    for (const r of result.results) {
      const school = mapSchool(r)
      const rows = mapPrograms(r)
      if (!school || rows.length === 0) continue
      pageSchools.push(school)
      pagePrograms.push(...rows)
    }
    // Schools first: each program row points to its school.
    await upsertSchools(prisma, pageSchools)
    await upsertPrograms(prisma, pagePrograms)
    schools += pageSchools.length
    programs += pagePrograms.length
    console.log(`page ${page + 1}/${Math.ceil(total / PER_PAGE)}: ${programs} programs at ${schools} schools`)
    page++
    await sleep(DELAY_MS)
  }

  console.log(`Done. ${programs} programs saved at ${schools} schools.`)
}

main()
  .catch((e) => {
    console.error(e)
    process.exit(1)
  })
  .finally(() => prisma.$disconnect())
