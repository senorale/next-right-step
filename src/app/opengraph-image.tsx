import { ImageResponse } from 'next/og'
import { readFile } from 'node:fs/promises'
import { join } from 'node:path'

// The card shown when a link to the site is shared (iMessage, Slack, LinkedIn, X).
export const alt = 'Next Right Step: a free financial tool to help you take your next right step'
export const size = { width: 1200, height: 630 }
export const contentType = 'image/png'

const INK = '#0f172a'
const MUTED = '#475569'
const BLUE = '#2563eb'
const BLUE_ON_DARK = '#60a5fa'

// The logo's winding route on a 64-unit grid: the path taken, two roads not
// taken, a dotted alternative, and the next step in blue. Same mark as icon.svg.
function Route({ ink, blue, width, viewBox, w = 6 }: { ink: string; blue: string; width: number; viewBox: string; w?: number }) {
  const [, , vw, vh] = viewBox.split(' ').map(Number)
  const line = { fill: 'none', strokeLinecap: 'round', strokeLinejoin: 'round' } as const
  return (
    <svg width={width} height={(width * vh) / vw} viewBox={viewBox}>
      <path d="M32 70V60C32 53 40 49 40 42S32 31 32 24" stroke={ink} strokeWidth={w} {...line} />
      <path d="M35.5 52Q29 49 24 44" stroke={ink} strokeOpacity={0.3} strokeWidth={w - 1} {...line} />
      <path d="M37.5 33Q42 30 47 27" stroke={ink} strokeOpacity={0.5} strokeWidth={w - 1} {...line} />
      <path d="M32 24Q32 16 22 10" stroke={ink} strokeOpacity={0.45} strokeWidth={w - 1} strokeDasharray={`0.1 ${w - 0.5}`} {...line} />
      <path d="M32 24Q32 16 42 10" stroke={blue} strokeWidth={w} {...line} />
      <circle cx="42" cy="10" r={w - 1} fill={blue} />
    </svg>
  )
}

export default async function Image() {
  const [medium, extraBold] = await Promise.all([
    readFile(join(process.cwd(), 'assets/fonts/Inter-Medium.ttf')),
    readFile(join(process.cwd(), 'assets/fonts/Inter-ExtraBold.ttf')),
  ])

  return new ImageResponse(
    (
      <div style={{ width: '100%', height: '100%', display: 'flex', background: '#f8fafc', fontFamily: 'Inter' }}>
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'space-between', padding: '64px 56px 60px 72px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <Route ink={INK} blue={BLUE} width={44} viewBox="4 -1 60 60" />
            <div style={{ fontSize: 30, fontWeight: 800, color: INK, letterSpacing: -0.5 }}>Next Right Step</div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 22 }}>
            <div style={{ display: 'flex', alignSelf: 'flex-start', fontSize: 22, fontWeight: 800, color: BLUE, background: '#dbeafe', padding: '6px 16px', borderRadius: 999, letterSpacing: 1 }}>
              FREE
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', fontSize: 62, fontWeight: 800, color: INK, lineHeight: 1.08, letterSpacing: -1.5 }}>
              A financial tool to help you take your <span style={{ color: BLUE }}>next right step.</span>
            </div>
            <div style={{ display: 'flex', fontSize: 27, fontWeight: 500, color: MUTED, lineHeight: 1.4 }}>
              Compare the real cost and payoff of college, trades, and careers, using U.S. government data.
            </div>
          </div>
        </div>

        <div style={{ width: 400, height: '100%', display: 'flex', background: INK, position: 'relative', overflow: 'hidden' }}>
          <div style={{ position: 'absolute', left: -70, top: 40, display: 'flex' }}>
            <Route ink="#f8fafc" blue={BLUE_ON_DARK} width={540} viewBox="4 -1 60 70" />
          </div>
        </div>
      </div>
    ),
    {
      ...size,
      fonts: [
        { name: 'Inter', data: medium, style: 'normal', weight: 500 },
        { name: 'Inter', data: extraBold, style: 'normal', weight: 800 },
      ],
    },
  )
}
