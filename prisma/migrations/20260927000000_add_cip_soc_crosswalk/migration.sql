-- CreateTable
CREATE TABLE "CipCode" (
    "id" TEXT NOT NULL,
    "code" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "CipCode_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "CipOccupation" (
    "id" TEXT NOT NULL,
    "cip_id" TEXT NOT NULL,
    "occupation_id" TEXT NOT NULL,

    CONSTRAINT "CipOccupation_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "CipCode_code_key" ON "CipCode"("code");

-- CreateIndex
CREATE INDEX "CipOccupation_cip_id_idx" ON "CipOccupation"("cip_id");

-- CreateIndex
CREATE INDEX "CipOccupation_occupation_id_idx" ON "CipOccupation"("occupation_id");

-- CreateIndex
CREATE UNIQUE INDEX "CipOccupation_cip_id_occupation_id_key" ON "CipOccupation"("cip_id", "occupation_id");

-- AddForeignKey
ALTER TABLE "CipOccupation" ADD CONSTRAINT "CipOccupation_cip_id_fkey" FOREIGN KEY ("cip_id") REFERENCES "CipCode"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "CipOccupation" ADD CONSTRAINT "CipOccupation_occupation_id_fkey" FOREIGN KEY ("occupation_id") REFERENCES "OccupationSubCategory"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
