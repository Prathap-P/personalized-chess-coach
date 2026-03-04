import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis,
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
} from 'recharts'
import type { ProfileAnalysis, PlayerStats } from '../types/analysis'

interface Props {
  profile: ProfileAnalysis
}

const RADAR_KEYS: (keyof PlayerStats)[] = [
  'best', 'excellent', 'good', 'inaccuracy', 'mistake', 'blunder',
]

const RADAR_LABELS: Record<string, string> = {
  best: 'Best', excellent: 'Excellent', good: 'Good',
  inaccuracy: 'Inaccuracy', mistake: 'Mistake', blunder: 'Blunder',
}

const SEV_COLOR: Record<string, string> = {
  high: '#ef4444',
  medium: '#f59e0b',
  low: '#22c55e',
}

const CustomTooltip = ({ active, payload }: { active?: boolean; payload?: { name: string; value: number }[] }) => {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-gray-900 border border-gray-700 rounded px-3 py-2 text-xs shadow-lg">
      {payload.map((p) => (
        <div key={p.name}>{p.name}: <span className="text-white font-medium">{p.value}</span></div>
      ))}
    </div>
  )
}

export default function ProfileCharts({ profile }: Props) {
  const { aggregated_stats: stats, patterns, opening_analysis: openingAnalysis } = profile

  // Radar data
  const radarData = RADAR_KEYS.map((key) => ({
    subject: RADAR_LABELS[key],
    value: stats[key] as number,
  }))

  // Opening bar data
  const openingData = Object.entries(openingAnalysis)
    .slice(0, 8)
    .map(([name, s]) => ({
      name: name.length > 16 ? name.slice(0, 14) + '…' : name,
      games: s.games,
      avg_errors: +s.avg_errors.toFixed(1),
    }))

  return (
    <div className="space-y-6">
      {/* Accuracy summary */}
      <div className="grid grid-cols-3 gap-4 text-center">
        <div className="card">
          <div className="text-3xl font-bold text-brand-400">{stats.accuracy.toFixed(1)}%</div>
          <div className="text-xs text-gray-500 mt-1">Avg Accuracy</div>
        </div>
        <div className="card">
          <div className="text-3xl font-bold text-red-400">{stats.blunder}</div>
          <div className="text-xs text-gray-500 mt-1">Blunders</div>
        </div>
        <div className="card">
          <div className="text-3xl font-bold text-green-400">{stats.best + stats.excellent}</div>
          <div className="text-xs text-gray-500 mt-1">Best / Excellent</div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Move quality radar */}
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-400 mb-4">Move Quality Distribution</h3>
          <ResponsiveContainer width="100%" height={240}>
            <RadarChart data={radarData}>
              <PolarGrid stroke="#374151" />
              <PolarAngleAxis dataKey="subject" tick={{ fill: '#9ca3af', fontSize: 11 }} />
              <Radar
                name="Moves"
                dataKey="value"
                stroke="#22c55e"
                fill="#22c55e"
                fillOpacity={0.25}
                strokeWidth={2}
              />
            </RadarChart>
          </ResponsiveContainer>
        </div>

        {/* Opening performance */}
        {openingData.length > 0 && (
          <div className="card">
            <h3 className="text-sm font-semibold text-gray-400 mb-4">Opening Performance</h3>
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={openingData} layout="vertical">
                <XAxis type="number" tick={{ fill: '#9ca3af', fontSize: 10 }} />
                <YAxis dataKey="name" type="category" width={90} tick={{ fill: '#9ca3af', fontSize: 10 }} />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="avg_errors" name="Avg Errors" radius={[0, 4, 4, 0]}>
                  {openingData.map((entry, i) => (
                    <Cell
                      key={i}
                      fill={entry.avg_errors > 3 ? '#ef4444' : entry.avg_errors > 1.5 ? '#f59e0b' : '#22c55e'}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* Patterns */}
      {patterns.length > 0 && (
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-400 mb-3">Identified Patterns</h3>
          <div className="space-y-2">
            {patterns.map((p, i) => (
              <div
                key={i}
                className="flex items-start justify-between p-3 bg-gray-800/40 rounded-lg border border-gray-800"
              >
                <div className="flex-1">
                  <div className="text-sm text-gray-200">{p.description}</div>
                  <div className="text-xs text-gray-500 mt-0.5">{p.occurrences} occurrences</div>
                </div>
                <span
                  className="badge ml-3 mt-0.5 flex-shrink-0"
                  style={{
                    backgroundColor: SEV_COLOR[p.severity] + '22',
                    color: SEV_COLOR[p.severity],
                    border: `1px solid ${SEV_COLOR[p.severity]}44`,
                  }}
                >
                  {p.severity}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
