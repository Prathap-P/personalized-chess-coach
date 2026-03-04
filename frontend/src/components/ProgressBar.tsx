import type { WsProgressMessage } from '../types/analysis'

interface Props {
  progress: WsProgressMessage | null
  label?: string
}

export default function ProgressBar({ progress, label }: Props) {
  const pct = progress?.percent ?? 0
  const current = progress?.current ?? 0
  const total = progress?.total ?? 0

  return (
    <div className="space-y-2">
      <div className="flex justify-between text-sm text-gray-400">
        <span>{label ?? 'Analyzing…'}</span>
        {total > 0 && (
          <span>
            {current} / {total}
          </span>
        )}
      </div>
      <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
        <div
          className="h-full bg-brand-500 rounded-full transition-all duration-300"
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="text-right text-xs text-gray-500">{pct.toFixed(0)}%</div>
    </div>
  )
}
