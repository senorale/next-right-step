-- Corrections to OccupationSubCategory.typical_years_of_school where the O*NET
-- education level -> years mapping (EDUCATION_CODE_TO_YEARS in api/db.py) is
-- wrong for a specific occupation. The backfill only fills empty values, so
-- these stick once applied. Run after seeding a fresh database:
--   psql "$DATABASE_URL" -f scripts/occupation-years-fixes.sql

-- Lawyers: 4 years undergrad + 3-year JD = 7 (the mapping gives 8 for any
-- first professional / doctoral degree). Applied to production on 2026-10-04.
UPDATE "OccupationSubCategory" SET typical_years_of_school = 7, updated_at = NOW() WHERE occupation_code = '23-1011';
