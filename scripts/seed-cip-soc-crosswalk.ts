// Seeds CipCode and CipOccupation from the NCES CIP2020-SOC2018 crosswalk.
// Additive and safe to rerun: CIP codes are upserted by code and links are
// inserted with skipDuplicates. Nothing is deleted.
import { PrismaClient } from "@prisma/client";
import { readFileSync } from "fs";
import { join } from "path";

const prisma = new PrismaClient();

// BLS OEWS publishes some occupations under combined codes that SOC 2018 (and
// so the crosswalk) splits. Detailed crosswalk code -> combined OEWS code.
const OEWS_COMBINED: Record<string, string> = {
  "21-1011": "21-1018", // Substance Abuse and Behavioral Disorder Counselors
  "21-1014": "21-1018", // Mental Health Counselors
  "25-2055": "25-2052", // Special Education Teachers, Kindergarten
  "25-2056": "25-2052", // Special Education Teachers, Elementary School
};

// Splits one CSV line, honoring double-quoted fields that contain commas
// (e.g. "Psychology, General.").
function splitCsvLine(line: string): string[] {
  const fields: string[] = [];
  let current = "";
  let quoted = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      if (quoted && line[i + 1] === '"') {
        current += '"';
        i++;
      } else {
        quoted = !quoted;
      }
    } else if (ch === "," && !quoted) {
      fields.push(current);
      current = "";
    } else {
      current += ch;
    }
  }
  fields.push(current);
  return fields;
}

function parseCsv(path: string): { cip_code: string; cip_title: string; soc_code: string }[] {
  const raw = readFileSync(path, "utf-8");
  const lines = raw.split(/\r?\n/).slice(1).filter(Boolean);
  return lines.map((line) => {
    const [cip_code, cip_title, soc_code] = splitCsvLine(line);
    return { cip_code, cip_title, soc_code };
  });
}

async function main() {
  const csvPath = join(__dirname, "..", "data", "cip_soc_crosswalk.csv");
  const rows = parseCsv(csvPath);
  console.log(`Loaded ${rows.length} crosswalk rows`);

  // SOC code -> DB ids. Our occupations include some BLS broad groups (codes
  // ending in 0, e.g. 13-1020) while the crosswalk uses detailed codes
  // (13-1021, 13-1022). Map each detailed code to its broad group too, when the
  // broad group is what we store and the detailed code is not.
  const allOccupations = await prisma.occupationSubCategory.findMany({
    select: { id: true, occupation_code: true },
  });
  const exact = new Map(allOccupations.map((o) => [o.occupation_code, o.id]));
  const broad = new Map(
    allOccupations
      .filter((o) => o.occupation_code.endsWith("0"))
      .map((o) => [o.occupation_code.slice(0, 6), o.id])
  );
  const socToIds = (soc: string): string[] => {
    const ids: string[] = [];
    const id = exact.get(soc) ?? broad.get(soc.slice(0, 6));
    if (id) ids.push(id);
    const aliasId = OEWS_COMBINED[soc] && exact.get(OEWS_COMBINED[soc]);
    if (aliasId) ids.push(aliasId);
    return ids;
  };
  console.log(`${exact.size} SOC codes in DB, ${broad.size} broad groups`);

  // Aggregate 6-digit CIP to 4-digit, collect unique occupation ids per 4-digit CIP
  const cipMap = new Map<string, { title: string; occupationIds: Set<string> }>();
  for (const row of rows) {
    // 6-digit CIP "04.0201" -> 4-digit "0402"
    const cip4 = row.cip_code.replace(".", "").substring(0, 4);
    if (!cipMap.has(cip4)) {
      cipMap.set(cip4, { title: row.cip_title.replace(/\.$/, ""), occupationIds: new Set() });
    }
    const entry = cipMap.get(cip4)!;
    // Use the XX.XX00 title when available, otherwise first seen
    if (row.cip_code.endsWith("00")) entry.title = row.cip_title.replace(/\.$/, "");
    for (const id of socToIds(row.soc_code)) entry.occupationIds.add(id);
  }
  console.log(`${cipMap.size} unique 4-digit CIP codes`);

  let cipCount = 0;
  let linkCount = 0;
  for (const [code, entry] of cipMap) {
    // Skip CIP codes with no matching occupation
    if (entry.occupationIds.size === 0) continue;

    const cip = await prisma.cipCode.upsert({
      where: { code },
      create: { code, title: entry.title },
      update: { title: entry.title },
    });
    cipCount++;

    const { count } = await prisma.cipOccupation.createMany({
      data: [...entry.occupationIds].map((occupation_id) => ({ cip_id: cip.id, occupation_id })),
      skipDuplicates: true,
    });
    linkCount += count;
  }

  console.log(`\nDone: ${cipCount} CIP codes upserted, ${linkCount} new CIP-SOC links`);
}

main()
  .catch((e) => {
    console.error(e);
    process.exit(1);
  })
  .finally(() => prisma.$disconnect());
