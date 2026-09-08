export default function TopBar({ statusText, ready }: { statusText: string; ready: boolean }) {
  return (
    <header className="flex items-center justify-between border-b border-white/10 bg-[#05070d]/70 px-4 py-3.5 backdrop-blur sm:px-8">
      <div className="sm:hidden flex items-center gap-2 text-white font-semibold">
        <span>👁️</span> Trinetra
      </div>
      <div className="hidden text-sm text-slate-400 sm:block">
        Nashik-Trimbakeshwar Kumbh Mela 2027 · Agent Platform
      </div>
      <div className="flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs">
        <span className={`h-2 w-2 rounded-full ${ready ? 'bg-emerald-400' : 'bg-red-400'} ${ready ? 'animate-pulse' : ''}`} />
        <span className="text-slate-300">{statusText}</span>
      </div>
    </header>
  )
}
