# Next Right Step

A tool for people trying to figure out their next right step: college, a new career, or staying put. 


We put unbiased, government-issued data in front of you so you can make the decision yourself. 

We won't push you toward any particular path.


Everything here comes from public U.S. government sources that have been available for years. We just don't think they're compiled and presented in a useful way anywhere else.

## Origin

Next Right Step started as **Should I Go?**, [Michael Branconier](https://github.com/mikebranc)'s idea, built in August 2024 ([mikebranc/should-i-go](https://github.com/mikebranc/should-i-go)). It was a college cost calculator: you entered your tuition, loan terms, expected salary, and years in school, and it showed what the degree would really cost and how long it would take to pay off.

[Alejandro Carvajal](https://github.com/senorale) joined in 2025 and grounded it in public data: BLS salaries by occupation, national medians to compare your own numbers against, and College Scorecard costs. 


In 2026 he added an AI counselor, then re-imagined the whole app around a wider question: not just "should I go to college?" but "what's my next right step?" That redesign became Next Right Step. This repository continues from Mike's original, with its full history.

Thank you, Mike, for the idea that started it and collaboration/ideation along the way.

## What's in the app

Two ways in, from the landing page:

- **Guided experience** (`/chat`): an AI counselor (Claude) asks about your situation, pulls the relevant data, and builds a personalized report.
- **Explore on your own** (`/explore`): five self-serve paths.
  - **College vs alternatives**: a bachelor's degree against trades and working right away, plus any career you add.
  - **Compare schools**: net price for your family income, graduation rate, debt, earnings, and payoff for up to 5 schools.
  - **Compare programs**: what graduates of each program at one school earn and borrow.
  - **Compare careers**: salary, education debt, and payoff, measured from where you are today.
  - **Path to a career**: the education you still need, what it costs, and how long until it pays off.

The **FAQ** (`/faq`) explains every data source and calculation.

## Data sources

| Data | Source | How it's loaded |
|---|---|---|
| Salaries by occupation | [BLS Occupational Employment and Wage Statistics](https://www.bls.gov/oes/), May 2024 national medians | Seeded from `data/national_data.csv` |
| Schools (net price by income, outcomes, debt, earnings) | [College Scorecard](https://collegescorecard.ed.gov/data/) API | Bachelor's schools seeded; others fetched on first search and stored |
| Programs at a school | College Scorecard API | Fetched the first time a school is opened, then stored |
| Median debt by degree field and credential | College Scorecard Field of Study file | Aggregated across schools at seed time |
| Degree fields to occupations | [NCES CIP-SOC crosswalk](https://nces.ed.gov/ipeds/cipcode/resources.aspx?y=56) | Seeded from `data/cip_soc_crosswalk.csv` |
| Typical years of school per occupation | [O*NET Web Services](https://services.onetcenter.org/) (USDOL/ETA) | Stored per occupation, backfilled from the API |

Data scripts are additive: they upsert or insert missing rows and never delete.

## How the numbers work

**Cost** is median student debt, not tuition. Debt is what students actually borrow and repay after grants, scholarships, and family help, and College Scorecard reports it per degree field and credential, so each career gets its own estimate. Careers that need a graduate degree add the national median bachelor's debt. When no related field reports debt, the app estimates from the broader field family and labels it. Compare schools is the exception: it uses each school's net price times years of school, assuming the full amount is borrowed.

**Payoff timeline**:

```
total cost = debt + loan interest + (starting salary x years in school)
payoff     = total cost / (new salary - starting salary)
```

- Loan interest: 6.5% over 20 years, how long borrowers typically take (the 10-year federal plan is the exception, not the norm).
- Starting salary: the $46,748 national median for a high school diploma by default, or your own salary or current job.
- Payoff is the number of working years for the higher salary to recover the total cost. If the new salary isn't higher, it doesn't pay off.

Constants live in `src/app/constants/college_related_constants.ts`, and the shared math in `src/app/components/paths/finance.ts` and `src/lib/career-cost.ts`.

## Tech stack

- **Frontend:** Next.js 16 (App Router, Turbopack), React 19, Tailwind, shadcn/ui, Recharts 3
- **Database:** PostgreSQL with Prisma 6
- **Counselor API** (`api/`): Python 3.13, FastAPI, Anthropic SDK

## Getting started

Prereqs: Node 20+, Python 3.13, PostgreSQL, and API keys for College Scorecard ([api.data.gov](https://api.data.gov/signup/)), O*NET, and Anthropic.

1. Install:
   ```bash
   git clone https://github.com/senorale/next-right-step.git
   cd next-right-step
   npm install
   ```
2. Copy `.env.example` to `.env` and fill it in. It lists what the frontend and the counselor API each need.
3. Apply migrations:
   ```bash
   npx prisma migrate deploy
   ```
4. Seed the database. The Field of Study CSV is large and gitignored; download `Most-Recent-Cohorts-Field-of-Study.csv` from [College Scorecard](https://collegescorecard.ed.gov/data/) into `data/` first.
   ```bash
   npm run create-db     # occupations and BLS salaries
   npm run seed-schools  # bachelor's-degree schools from the Scorecard API
   TS_NODE_COMPILER_OPTIONS='{"module":"CommonJS","moduleResolution":"node"}' \
     node --env-file=.env -r ts-node/register/transpile-only scripts/seed-cip-soc-crosswalk.ts
   TS_NODE_COMPILER_OPTIONS='{"module":"CommonJS","moduleResolution":"node"}' \
     node --env-file=.env -r ts-node/register/transpile-only scripts/seed-program-debt.ts
   ```
5. Run the frontend:
   ```bash
   npm run dev
   ```
6. Run the counselor API (for `/chat`):
   ```bash
   cd api
   python -m venv venv && source venv/bin/activate
   pip install -r requirements.txt
   uvicorn main:app --reload --port 8000
   ```

Open [http://localhost:3000](http://localhost:3000).

## Disclaimer

Estimates from national medians and simplifying assumptions, not financial advice. Your own costs, aid, salary, and loan terms will differ.
