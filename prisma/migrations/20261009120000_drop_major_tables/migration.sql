-- DropForeignKey
ALTER TABLE "MajorOccupation" DROP CONSTRAINT "MajorOccupation_major_id_fkey";

-- DropForeignKey
ALTER TABLE "MajorOccupation" DROP CONSTRAINT "MajorOccupation_occupation_id_fkey";

-- DropTable
DROP TABLE "Major";

-- DropTable
DROP TABLE "MajorOccupation";

