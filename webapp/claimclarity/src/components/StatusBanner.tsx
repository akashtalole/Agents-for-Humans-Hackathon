import type { StatusBadge } from '../types'

const STYLES: Record<StatusBadge['level'], { wrap: string; icon: string }> = {
  error: {
    wrap: 'border-red-300 bg-red-50 text-red-800 dark:border-red-900 dark:bg-red-950/50 dark:text-red-300',
    icon: '⛔',
  },
  warning: {
    wrap:
      'border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950/50 dark:text-amber-300',
    icon: '⚠️',
  },
  success: {
    wrap:
      'border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950/50 dark:text-emerald-300',
    icon: '✅',
  },
  info: {
    wrap: 'border-blue-300 bg-blue-50 text-blue-800 dark:border-blue-900 dark:bg-blue-950/50 dark:text-blue-300',
    icon: 'ℹ️',
  },
}

export default function StatusBanner({ badge }: { badge: StatusBadge }) {
  const style = STYLES[badge.level]
  return (
    <div className={`flex items-start gap-2 rounded-xl border px-4 py-3 text-sm font-medium ${style.wrap}`}>
      <span aria-hidden="true">{style.icon}</span>
      <span>{badge.message}</span>
    </div>
  )
}
