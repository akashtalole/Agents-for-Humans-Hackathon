import type { Ghat, Route, TickGhatState } from '../types'
import { RISK_COLOR, riskFromPct } from './ui'

// Hand-placed schematic layout (not a real map projection - Trinetra has no
// GPS coordinates for these sites) chosen to read clearly as a small
// network diagram: the Kalaram Marg -> Ramkund -> Panchavati corridor left
// to right, Kushavarta (a separate town, Trimbakeshwar) offset to the
// lower right. Falls back to a simple grid for any ghat id not listed here
// so the diagram never breaks if the bundled site data changes.
const POSITIONS: Record<string, { x: number; y: number }> = {
  kalaram_marg: { x: 14, y: 52 },
  ramkund: { x: 42, y: 46 },
  panchavati_godavari: { x: 70, y: 26 },
  kushavarta: { x: 78, y: 78 },
}

function positionFor(id: string, index: number): { x: number; y: number } {
  if (POSITIONS[id]) return POSITIONS[id]
  const col = index % 3
  const row = Math.floor(index / 3)
  return { x: 20 + col * 30, y: 25 + row * 30 }
}

export default function NetworkDiagram({
  ghats,
  routes,
  liveState,
  activeGhatIds,
}: {
  ghats: Ghat[]
  routes: Route[]
  liveState: Record<string, TickGhatState>
  activeGhatIds: string[]
}) {
  const positioned = ghats.map((g, i) => ({ ghat: g, pos: positionFor(g.id, i) }))
  const posById = Object.fromEntries(positioned.map((p) => [p.ghat.id, p.pos]))

  const edges = routes
    .filter((r) => r.connects.length === 2 && posById[r.connects[0]] && posById[r.connects[1]])
    .map((r) => ({ route: r, a: posById[r.connects[0]], b: posById[r.connects[1]] }))

  const stubs = routes
    .filter((r) => r.connects.length === 1 && posById[r.connects[0]])
    .map((r) => ({ route: r, at: posById[r.connects[0]] }))

  return (
    <svg viewBox="0 0 100 100" className="h-full w-full">
      <defs>
        <radialGradient id="nodeGlowRoutine" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor={RISK_COLOR.routine} stopOpacity="0.35" />
          <stop offset="100%" stopColor={RISK_COLOR.routine} stopOpacity="0" />
        </radialGradient>
        <radialGradient id="nodeGlowElevated" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor={RISK_COLOR.elevated} stopOpacity="0.4" />
          <stop offset="100%" stopColor={RISK_COLOR.elevated} stopOpacity="0" />
        </radialGradient>
        <radialGradient id="nodeGlowCritical" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor={RISK_COLOR.critical} stopOpacity="0.5" />
          <stop offset="100%" stopColor={RISK_COLOR.critical} stopOpacity="0" />
        </radialGradient>
      </defs>

      {/* edges */}
      {edges.map(({ route, a, b }) => {
        const aState = liveState[route.connects[0]]
        const bState = liveState[route.connects[1]]
        const busy = (aState?.pct_of_capacity ?? 0) >= 85 || (bState?.pct_of_capacity ?? 0) >= 85
        return (
          <line
            key={route.id}
            x1={a.x}
            y1={a.y}
            x2={b.x}
            y2={b.y}
            stroke={busy ? RISK_COLOR.elevated : 'rgba(148,163,184,0.35)'}
            strokeWidth={busy ? 1.4 : 0.8}
            strokeDasharray={route.one_way ? '2 1.2' : undefined}
            className="transition-all duration-300"
          />
        )
      })}
      {stubs.map(({ route, at }) => (
        <line
          key={route.id}
          x1={at.x - 10}
          y1={at.y - 10}
          x2={at.x}
          y2={at.y}
          stroke="rgba(148,163,184,0.25)"
          strokeWidth={0.6}
          strokeDasharray="1.5 1.5"
        />
      ))}

      {/* nodes */}
      {positioned.map(({ ghat, pos }) => {
        const state = liveState[ghat.id]
        const pct = state?.pct_of_capacity ?? 0
        const risk = riskFromPct(pct)
        const isActive = activeGhatIds.includes(ghat.id)
        const radius = 5 + Math.min(pct, 200) / 200 * 5.5
        const glowId = risk === 'critical' ? 'nodeGlowCritical' : risk === 'elevated' ? 'nodeGlowElevated' : 'nodeGlowRoutine'

        return (
          <g key={ghat.id} transform={`translate(${pos.x}, ${pos.y})`}>
            {isActive && <circle r={radius + 8} fill={`url(#${glowId})`} />}
            {isActive && risk === 'critical' && (
              <circle r={radius} fill="none" stroke={RISK_COLOR.critical} strokeWidth={0.6} className="animate-pulse-ring origin-center" />
            )}
            <circle
              r={radius}
              fill={isActive ? RISK_COLOR[risk] : 'rgba(100,116,139,0.35)'}
              fillOpacity={isActive ? 0.85 : 0.5}
              stroke={isActive ? RISK_COLOR[risk] : 'rgba(148,163,184,0.4)'}
              strokeWidth={0.5}
              className="transition-all duration-300 ease-out"
            />
            <text y={radius + 5.5} textAnchor="middle" className="fill-slate-300" style={{ fontSize: '3.1px' }}>
              {ghat.name.split(' ').slice(0, 2).join(' ')}
            </text>
            {isActive && (
              <text y={1} textAnchor="middle" className="fill-white font-semibold" style={{ fontSize: '2.6px' }}>
                {pct.toFixed(0)}%
              </text>
            )}
          </g>
        )
      })}
    </svg>
  )
}
