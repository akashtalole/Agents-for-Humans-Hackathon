import type { StatusBadge } from '../types'

const STYLES: Record<StatusBadge['level'], string> = {
  error:
    'border-red-300 bg-red-50 text-red-900 dark:border-red-800 dark:bg-red-950/50 dark:text-red-200',
  warning:
    'border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-800 dark:bg-amber-950/50 dark:text-amber-200',
  success:
    'border-emerald-300 bg-emerald-50 text-emerald-900 dark:border-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-200',
}

const ICONS: Record<StatusBadge['level'], string> = {
  error: '🔴',
  warning: '🟡',
  success: '🟢',
}

export default function StatusBadgeBanner({ badge }: { badge: StatusBadge }) {
  return (
    <div className={`rounded-lg border px-4 py-3 text-sm font-medium ${STYLES[badge.level]}`}>
      <span aria-hidden="true" className="mr-1.5">
        {ICONS[badge.level]}
      </span>
      {badge.message}
    </div>
  )
}
