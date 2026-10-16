-- Deletes rows stored before the seeds and live fetches skipped rows with
-- nothing to compare. Same rules as mapPrograms and hasSchoolData in
-- src/lib/scorecard.ts:
--   a program needs earnings 1 or 4 years after graduating;
--   a school needs to be operating, with school-wide earnings and debt or at
--   least one program left (deleting a school cascades to its programs).
-- Safe to rerun: a second run deletes nothing.
BEGIN;

DELETE FROM "SchoolProgram"
WHERE earnings_1yr IS NULL AND earnings_4yr IS NULL;

DELETE FROM "School" s
WHERE NOT s.operating
   OR ((s.earnings_10yr IS NULL OR s.median_debt IS NULL)
       AND NOT EXISTS (SELECT 1 FROM "SchoolProgram" p WHERE p.school_id = s.school_id));

COMMIT;
