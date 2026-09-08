import type { ViewKey } from '../App'

const NAV: { key: ViewKey; label: string; hindi: string; icon: string }[] = [
  { key: 'overview', label: 'Overview', hindi: 'सारांश', icon: '◈' },
  { key: 'pilgrim', label: 'Yatri Netra', hindi: 'यात्री नेत्र', icon: '🧑‍🤝‍🧑' },
  { key: 'admin', label: 'Prashasan Netra', hindi: 'प्रशासन नेत्र', icon: '🛡️' },
  { key: 'twin', label: 'Bhavishya Netra', hindi: 'भविष्य नेत्र', icon: '🔮' },
  { key: 'calibration', label: 'Calibration', hindi: 'सत्यापन', icon: '✓' },
]

export default function Sidebar({ view, onChange }: { view: ViewKey; onChange: (v: ViewKey) => void }) {
  return (
    <aside className="hidden w-64 shrink-0 border-r border-white/10 bg-[#070a12]/80 backdrop-blur sm:flex sm:flex-col">
      <div className="flex items-center gap-3 px-5 py-6">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-saffron-400 to-saffron-600 text-lg shadow-glow">
          👁️
        </div>
        <div>
          <div className="text-lg font-semibold tracking-tight text-white">Trinetra</div>
          <div className="text-[11px] uppercase tracking-widest text-slate-500">त्रिनेत्र · Kumbh 2027</div>
        </div>
      </div>

      <nav className="flex-1 space-y-1 px-3 py-2">
        {NAV.map((item) => {
          const active = view === item.key
          return (
            <button
              key={item.key}
              onClick={() => onChange(item.key)}
              className={`group flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm font-medium transition ${
                active
                  ? 'bg-gradient-to-r from-saffron-500/20 to-transparent text-saffron-200 shadow-[inset_2px_0_0_0_theme(colors.saffron.400)]'
                  : 'text-slate-400 hover:bg-white/5 hover:text-slate-100'
              }`}
            >
              <span className="text-base">{item.icon}</span>
              <span className="flex flex-col leading-tight">
                <span>{item.label}</span>
                <span className={`text-[10px] ${active ? 'text-saffron-300/70' : 'text-slate-600'}`}>{item.hindi}</span>
              </span>
            </button>
          )
        })}
      </nav>

      <div className="border-t border-white/10 px-5 py-4 text-[11px] leading-relaxed text-slate-600">
        Decision support for Nashik-Trimbakeshwar Simhastha 2027 — never an autonomous authority.
      </div>
    </aside>
  )
}
