import { PrismaClient } from "@prisma/client";
import { readFileSync } from "fs";
import { join } from "path";

const prisma = new PrismaClient();

function parseCsv(path: string): { cip_code: string; cip_title: string; soc_code: string }[] {
  const raw = readFileSync(path, "utf-8");
  const lines = raw.split("\n").slice(1).filter(Boolean);
  return lines.map((line) => {
    const [cip_code, cip_title, soc_code] = line.split(",").map((s) => s.replace(/^"|"$/g, ""));
    return { cip_code, cip_title, soc_code };
  });
}

async function main() {
  const csvPath = join(__dirname, "..", "data", "cip_soc_crosswalk.csv");
  const rows = parseCsv(csvPath);
  console.log(`Loaded ${rows.length} crosswalk rows`);

  // Build SOC code -> DB id lookup
  const allOccupations = await prisma.occupationSubCategory.findMany({
    select: { id: true, occupation_code: true },
  });
  const socToId = new Map(allOccupations.map((o) => [o.occupation_code, o.id]));
  console.log(`${socToId.size} SOC codes in DB`);

  // Aggregate 6-digit CIP to 4-digit, collect unique SOC links per 4-digit CIP
  const cipMap = new Map<string, { title: string; socCodes: Set<string> }>();

  for (const row of rows) {
    // 6-digit CIP "04.0201" -> 4-digit "0402"
    const cip4 = row.cip_code.replace(".", "").substring(0, 4);
    // Use the XX.00 title when available, otherwise first seen
    const is00 = row.cip_code.endsWith("00");

    if (!cipMap.has(cip4)) {
      cipMap.set(cip4, { title: row.cip_title.replace(/\.$/, ""), socCodes: new Set() });
    }

    const entry = cipMap.get(cip4)!;
    if (is00) {
      entry.title = row.cip_title.replace(/\.$/, "");
    }
    entry.socCodes.add(row.soc_code);
  }

  console.log(`${cipMap.size} unique 4-digit CIP codes`);

  // Count how many SOC codes we can match
  let matchedLinks = 0;
  let unmatchedSoc = 0;

  for (const [, entry] of cipMap) {
    for (const soc of entry.socCodes) {
      if (socToId.has(soc)) matchedLinks++;
      else unmatchedSoc++;
    }
  }
  console.log(`${matchedLinks} CIP-SOC links match our DB, ${unmatchedSoc} SOC codes not in DB`);

  // Clear existing data
  await prisma.cipOccupation.deleteMany();
  await prisma.cipCode.deleteMany();
  console.log("\nCleared existing CIP data");

  // Insert CIP codes
  let cipCount = 0;
  for (const [code, entry] of cipMap) {
    // Skip CIP codes with zero matching SOC codes
    const matchingSocs = [...entry.socCodes].filter((s) => socToId.has(s));
    if (matchingSocs.length === 0) continue;

    await prisma.cipCode.create({
      data: { code, title: entry.title },
    });
    cipCount++;
  }
  console.log(`Inserted ${cipCount} CIP codes`);

  // Insert CIP-SOC links
  let linkCount = 0;
  for (const [code, entry] of cipMap) {
    const cip = await prisma.cipCode.findUnique({ where: { code } });
    if (!cip) continue;

    for (const soc of entry.socCodes) {
      const occupationId = socToId.get(soc);
      if (!occupationId) continue;

      await prisma.cipOccupation.create({
        data: { cip_id: cip.id, occupation_id: occupationId },
      });
      linkCount++;
    }

    if (linkCount % 200 === 0) console.log(`  ... ${linkCount} links`);
  }

  console.log(`\nDone: ${cipCount} CIP codes, ${linkCount} CIP-SOC links`);
}

main()
  .catch((e) => {
    console.error(e);
    process.exit(1);
  })
  .finally(() => prisma.$disconnect());
