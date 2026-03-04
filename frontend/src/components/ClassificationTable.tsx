import type { PlayerStats } from '../types/analysis'

interface Props {
  whiteName: string
  blackName: string
  whiteStats: PlayerStats
  blackStats: PlayerStats
}

const ROWS: [string, string, keyof PlayerStats][] = [
  ['✨', 'Brilliant',  'brilliant'],
  ['🎯', 'Great',      'great'],
  ['⭐', 'Best',       'best'],
  ['👍', 'Excellent',  'excellent'],
  ['✅', 'Good',       'good'],
  ['⚠️', 'Inaccuracy', 'inaccuracy'],
  ['❌', 'Mistake',    'mistake'],
  ['💥', 'Blunder',    'blunder'],
]

const COLOR_MAP: Record<string, string> = {
  brilliant:  'text-purple-400',
  great:      'text-cyan-400',
  best:       'text-brand-400',
  excellent:  'text-green-400',
  good:       'text-gray-300',
  inaccuracy: 'text-yellow-400',
  mistake:    'text-orange-400',
  blunder:    'text-red-500',
}

function AccuracyPill({ value }: { value: number }) {
  const color =
    value >= 90 ? 'bg-green-500/20 text-green-300' :
    value >= 75 ? 'bg-brand-500/20 text-brand-300' :
    value >= 60 ? 'bg-yellow-500/20 text-yellow-300' :
                  'bg-red-500/20 text-red-300'
  return (
    <span className={`badge ${color} text-base font-bold px-3 py-1`}>
      {value.toFixed(1)}%
    </span>
  )
}

export default function ClassificationTable({ whiteName, blackName, whiteStats, blackStats }: Props) {
  return (
    <div className="space-y-4">
      {/* Accuracy banner */}
      <div className="grid grid-cols-3 items-center text-center gap-2">
        <div>
          <div className="text-sm text-gray-400 mb-1 truncate">{whiteName}</div>
          <AccuracyPill value={whiteStats.accuracy} />
        </div>
        <div className="text-xs text-gray-600 font-medium">ACCURACY</div>
        <div>
          <div className="text-sm text-gray-400 mb-1 truncate">{blackName}</div>
          <AccuracyPill value={blackStats.accuracy} />
        </div>
      </div>

      {/* Classification breakdown */}
      <div className="overflow-hidden rounded-lg border border-gray-800">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-800/60 text-gray-400 text-xs uppercase tracking-wide">
              <th className="py-2 pl-4 text-left">Move Quality</th>
              <th className="py-2 pr-4 text-center w-20">{whiteName.split(' ')[0]}</th>
              <th className="py-2 pr-4 text-center w-20">{blackName.split(' ')[0]}</th>
            </tr>
          </thead>
          <tbody>
            {ROWS.map(([emoji, label, key]) => {
              const wv = whiteStats[key] as number
              const bv = blackStats[key] as number
              const cls = COLOR_MAP[key] ?? 'text-gray-300'
              return (
                <tr key={key} className="border-t border-gray-800/60 hover:bg-gray-800/30 transition-colors">
                  <td className="py-2 pl-4 text-gray-300">
                    {emoji} {label}
                  </td>
                  <td className={`py-2 pr-4 text-center font-medium ${wv > 0 ? cls : 'text-gray-700'}`}>
                    {wv}
                  </td>
                  <td className={`py-2 pr-4 text-center font-medium ${bv > 0 ? cls : 'text-gray-700'}`}>
                    {bv}
                  </td>
                </tr>
              )
            })}
            <tr className="border-t border-gray-700 bg-gray-800/40 text-xs text-gray-500">
              <td className="py-2 pl-4">Total / Avg Loss</td>
              <td className="py-2 pr-4 text-center">
                {whiteStats.total_moves} · {whiteStats.average_eval_loss.toFixed(1)} cp
              </td>
              <td className="py-2 pr-4 text-center">
                {blackStats.total_moves} · {blackStats.average_eval_loss.toFixed(1)} cp
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  )
}
