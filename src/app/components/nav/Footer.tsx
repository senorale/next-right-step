const TWITTER_LINK = 'https://x.com/mike_branc'
const ALE_LINKED_IN = 'https://www.linkedin.com/in/alejandro-carvajal-916b55190/'

export default function Footer() {
  return (
    <footer className="border-t bg-card px-4 py-6 text-xs text-muted-foreground">
      <ul className="mx-auto max-w-4xl space-y-1">
        <li>
          Salaries:{' '}
          <a href="https://www.bls.gov/oes/" target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
            U.S. Bureau of Labor Statistics
          </a>{' '}
          (May 2024)
        </li>
        <li>
          School costs, graduation rates, and program earnings:{' '}
          <a href="https://collegescorecard.ed.gov/data/" target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
            U.S. Department of Education College Scorecard
          </a>
        </li>
        <li>
          Education requirements:{' '}
          <a href="https://services.onetcenter.org/" target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
            O*NET Web Services
          </a>{' '}
          (USDOL/ETA)
        </li>
      </ul>
      <div className="mx-auto mt-4 max-w-4xl space-y-1">
        <p>
          Every figure here is illustrative, based on national medians and simplifying assumptions. Look up current
          numbers for your own situation. This isn&apos;t financial advice or a prediction of your outcome.
        </p>
        <p>
          Created by{' '}
          <a href={TWITTER_LINK} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
            Michael Branconier
          </a>{' '}
          &{' '}
          <a href={ALE_LINKED_IN} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
            Alejandro Carvajal
          </a>
        </p>
      </div>
    </footer>
  )
}
