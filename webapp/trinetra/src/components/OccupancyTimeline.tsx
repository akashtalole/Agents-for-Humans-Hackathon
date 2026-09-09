import type { Ghat } from '../types'
import { RISK_COLOR, riskFromPct } from './ui'

export interface TimelinePoint {
  minute: number
  pct: Record<string, number>
}

export default function OccupancyTimeline({
  ghats,
  activeGhatIds,
  history,
  durationMinutes,
}: {
  ghats: Ghat[]
  activeGhatIds: string[]
  history: TimelinePoint[]
  durationMinutes: number
}) {
  const activeGhats = ghats.filter((g) => activeGhatIds.includes(g.id))
  const width = 100
  const height = 40
  const maxPct = Math.max(150, ...history.flatMap((h) => activeGhatIds.map((id) => h.pct[id] ?? 0)))

  function pathFor(ghatId: string): string {
    if (history.length === 0) return ''
    return history
      .map((h, i) => {
        const x = durationMinutes > 0 ? (h.minute / Math.max(durationMinutes - 1, 1)) * width : 0
        const y = height - (Math.min(h.pct[ghatId] ?? 0, maxPct) / maxPct) * height
        return `${i === 0 ? 'M' : 'L'}${x.toFixed(2)},${y.toFixed(2)}`
      })
      .join(' ')
  }

  const thresholdY = (t: number) => height - (Math.min(t, maxPct) / maxPct) * height
  const palette = ['#38bdf8', '#c084fc', '#fb923c', '#4ade80']

  return (
    <div>
      <svg viewBox={`0 0 ${width} ${height}`} className="h-40 w-full overflow-visible">
        {/* threshold guides */}
        <line x1={0} x2={width} y1={thresholdY(85)} y2={thresholdY(85)} stroke={RISK_COLOR.elevated} strokeOpacity={0.3} strokeDasharray="1.5 1.5" strokeWidth={0.3} />
        <line x1={0} x2={width} y1={thresholdY(110)} y2={thresholdY(110)} stroke={RISK_COLOR.critical} strokeOpacity={0.3} strokeDasharray="1.5 1.5" strokeWidth={0.3} />

        {activeGhats.map((g, i) => (
          <path key={g.id} d={pathFor(g.id)} fill="none" stroke={palette[i % palette.length]} strokeWidth={0.6} />
        ))}
      </svg>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
        {activeGhats.map((g, i) => {
          const last = history[history.length - 1]
          const pct = last?.pct[g.id] ?? 0
          return (
            <div key={g.id} className="flex items-center gap-1.5 text-xs">
              <span className="h-2 w-2 rounded-full" style={{ backgroundColor: palette[i % palette.length] }} />
              <span className="text-slate-400">{g.name}</span>
              <span className="font-semibold" style={{ color: RISK_COLOR[riskFromPct(pct)] }}>
                {pct.toFixed(0)}%
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
