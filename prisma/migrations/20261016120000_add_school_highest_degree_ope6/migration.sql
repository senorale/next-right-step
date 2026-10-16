-- AlterTable
ALTER TABLE "School" ADD COLUMN     "highest_degree" INTEGER,
ADD COLUMN     "ope6_id" TEXT;

-- CreateIndex
CREATE INDEX "School_ope6_id_idx" ON "School"("ope6_id");
