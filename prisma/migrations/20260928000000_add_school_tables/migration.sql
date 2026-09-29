-- CreateTable
CREATE TABLE "School" (
    "school_id" INTEGER NOT NULL,
    "name" TEXT NOT NULL,
    "city" TEXT NOT NULL,
    "state" TEXT NOT NULL,
    "school_type" TEXT NOT NULL,
    "url" TEXT,
    "student_size" INTEGER,
    "tuition_in_state" INTEGER,
    "tuition_out_of_state" INTEGER,
    "avg_net_price" INTEGER,
    "net_price_by_income" JSONB,
    "graduation_rate" DOUBLE PRECISION,
    "median_debt" INTEGER,
    "earnings_6yr" INTEGER,
    "earnings_10yr" INTEGER,
    "admission_rate" DOUBLE PRECISION,
    "retention_rate" DOUBLE PRECISION,
    "repayment_rate_3yr" DOUBLE PRECISION,
    "fetched_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "School_pkey" PRIMARY KEY ("school_id")
);

-- CreateTable
CREATE TABLE "SchoolProgram" (
    "id" TEXT NOT NULL,
    "school_id" INTEGER NOT NULL,
    "cip_code" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "credential_level" INTEGER NOT NULL,
    "earnings_1yr" INTEGER,
    "earnings_4yr" INTEGER,
    "median_debt" INTEGER,
    "fetched_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "SchoolProgram_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "School_name_idx" ON "School"("name");

-- CreateIndex
CREATE INDEX "School_state_idx" ON "School"("state");

-- CreateIndex
CREATE INDEX "SchoolProgram_cip_code_idx" ON "SchoolProgram"("cip_code");

-- CreateIndex
CREATE UNIQUE INDEX "SchoolProgram_school_id_cip_code_credential_level_key" ON "SchoolProgram"("school_id", "cip_code", "credential_level");

-- AddForeignKey
ALTER TABLE "SchoolProgram" ADD CONSTRAINT "SchoolProgram_school_id_fkey" FOREIGN KEY ("school_id") REFERENCES "School"("school_id") ON DELETE CASCADE ON UPDATE CASCADE;

