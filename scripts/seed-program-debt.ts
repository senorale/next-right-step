import fs from 'fs'
import path from 'path'
import { parse } from 'csv-parse'
import { PrismaClient } from '@prisma/client'

const prisma = new PrismaClient()

const CSV_PATH = path.join(
  process.cwd(),
  'data',
  'Most-Recent-Cohorts-Field-of-Study.csv'
)

const CREDENTIAL_LABELS: Record<string, string> = {
  '1': 'Undergraduate Certificate',
  '2': "Associate's Degree",
  '3': "Bachelor's Degree",
  '4': 'Post-Baccalaureate Certificate',
  '5': "Master's Degree",
  '6': 'Doctoral Degree',
  '7': 'First Professional Degree',
  '8': 'Graduate/Professional Certificate',
}

const CONTROL_MAP: Record<string, string> = {
  '1': 'public',
  '2': 'private_nonprofit',
  Public: 'public',
  'Private, nonprofit': 'private_nonprofit',
}

function toFloat(v: string | undefined): number | null {
  if (v == null) return null
  const s = v.trim()
  if (s === '' || s === 'NULL' || s === 'PrivacySuppressed' || s === 'PS' || s === 'NA')
    return null
  const n = Number(s)
  return Number.isFinite(n) ? n : null
}

function median(arr: number[]): number {
  const sorted = [...arr].sort((a, b) => a - b)
  const mid = Math.floor(sorted.length / 2)
  return sorted.length % 2 ? sorted[mid] : Math.round((sorted[mid - 1] + sorted[mid]) / 2)
}

function mean(arr: number[]): number {
  return Math.round(arr.reduce((s, v) => s + v, 0) / arr.length)
}

type DebtBucket = { debts: number[]; means: number[] }

async function main() {
  const cipCodes = await prisma.cipCode.findMany({ select: { id: true, code: true } })
  const cipByCode = new Map(cipCodes.map((c) => [c.code, c.id]))
  console.log(`Loaded ${cipByCode.size} CIP codes from DB`)

  const grouped = new Map<string, Map<string, Map<string, DebtBucket>>>()

  await new Promise<void>((resolve, reject) => {
    const parser = fs
      .createReadStream(CSV_PATH)
      .pipe(parse({ columns: true, skip_empty_lines: true }))

    parser.on('data', (row: Record<string, string>) => {
      const cipCode = (row.CIPCODE ?? '').replace('.', '')
      if (!cipByCode.has(cipCode)) return

      const credLevel = row.CREDLEV
      if (!CREDENTIAL_LABELS[credLevel]) return

      const control = row.CONTROL
      const schoolType = CONTROL_MAP[control]
      if (!schoolType) return

      const debtMedian = toFloat(row.DEBT_ALL_STGP_EVAL_MDN)
      const debtMean = toFloat(row.DEBT_ALL_STGP_EVAL_MEAN)
      if (debtMedian == null) return

      if (!grouped.has(cipCode)) grouped.set(cipCode, new Map())
      const byCredLevel = grouped.get(cipCode)!
      if (!byCredLevel.has(credLevel)) byCredLevel.set(credLevel, new Map())
      const byControl = byCredLevel.get(credLevel)!

      if (!byControl.has(schoolType))
        byControl.set(schoolType, { debts: [], means: [] })
      const bucket = byControl.get(schoolType)!
      bucket.debts.push(debtMedian)
      if (debtMean != null) bucket.means.push(debtMean)

      if (!byControl.has('all')) byControl.set('all', { debts: [], means: [] })
      const allBucket = byControl.get('all')!
      allBucket.debts.push(debtMedian)
      if (debtMean != null) allBucket.means.push(debtMean)
    })

    parser.on('end', resolve)
    parser.on('error', reject)
  })

  console.log(`Grouped ${grouped.size} CIP codes with debt data`)

  let upserted = 0
  for (const [cipCode, byCredLevel] of grouped) {
    const cipId = cipByCode.get(cipCode)!
    for (const [credLevel, byControl] of byCredLevel) {
      for (const [schoolType, bucket] of byControl) {
        const credLevelNum = parseInt(credLevel, 10)
        await prisma.programDebt.upsert({
          where: {
            cip_id_credential_level_school_type: {
              cip_id: cipId,
              credential_level: credLevelNum,
              school_type: schoolType,
            },
          },
          create: {
            cip_id: cipId,
            credential_level: credLevelNum,
            credential_label: CREDENTIAL_LABELS[credLevel],
            school_type: schoolType,
            median_debt: median(bucket.debts),
            mean_debt: bucket.means.length ? mean(bucket.means) : null,
            sample_size: bucket.debts.length,
          },
          update: {
            credential_label: CREDENTIAL_LABELS[credLevel],
            median_debt: median(bucket.debts),
            mean_debt: bucket.means.length ? mean(bucket.means) : null,
            sample_size: bucket.debts.length,
          },
        })
        upserted++
      }
    }
  }

  console.log(`Upserted ${upserted} ProgramDebt rows`)
}

main()
  .then(() => console.log('Program debt seeded.'))
  .catch((e) => {
    console.error(e)
    process.exit(1)
  })
  .finally(() => prisma.$disconnect())
