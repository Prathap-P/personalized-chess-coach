import type { MoveExplanation } from '../types/analysis'

interface Props {
  moveSan: string
  explanation: MoveExplanation | null
  loading: boolean
  error: string | null
}

const MOTIF_LABELS: Record<string, string> = {
  fork: '⚔️ Fork',
  pin: '📌 Pin',
  skewer: '🗡️ Skewer',
  discovered_attack: '💥 Discovered Attack',
  back_rank: '🏰 Back Rank',
  removal_of_defender: '🛡️ Removal of Defender',
  zwischenzug: '⚡ Zwischenzug',
}

const PHASE_LABELS: Record<string, string> = {
  opening: 'Opening',
  middlegame: 'Middlegame',
  endgame: 'Endgame',
}

export default function MoveExplanationPanel({ moveSan, explanation, loading, error }: Props) {
  if (!moveSan) return null

  return (
    <div className="card space-y-4 text-sm">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-gray-300">
          Move Analysis — <span className="font-mono text-white">{moveSan}</span>
        </h3>
        <div className="flex items-center gap-2">
          {explanation?.game_phase && (
            <span className="text-xs text-gray-500 bg-gray-800 px-2 py-0.5 rounded">
              {PHASE_LABELS[explanation.game_phase] ?? explanation.game_phase}
            </span>
          )}
          {explanation?.tactical_motif && (
            <span className="text-xs bg-yellow-500/20 text-yellow-400 px-2 py-0.5 rounded border border-yellow-600/40">
              {MOTIF_LABELS[explanation.tactical_motif] ?? explanation.tactical_motif}
            </span>
          )}
          {explanation?.is_fallback && (
            <span className="text-xs text-gray-600 italic">template</span>
          )}
        </div>
      </div>

      {/* Loading skeleton */}
      {loading && (
        <div className="space-y-2 animate-pulse">
          <div className="h-3 bg-gray-700 rounded w-3/4" />
          <div className="h-3 bg-gray-700 rounded w-full" />
          <div className="h-3 bg-gray-700 rounded w-5/6" />
        </div>
      )}

      {/* Error */}
      {error && !loading && (
        <p className="text-red-400 text-xs">{error}</p>
      )}

      {/* Content */}
      {explanation && !loading && (
        <div className="space-y-4">
          {/* What the move does */}
          {explanation.move_intent && (
            <Section label="What this move does">
              {explanation.move_intent}
            </Section>
          )}

          {/* Why it's bad */}
          {explanation.why_bad && (
            <Section label="Why it's a problem" accent="red">
              {explanation.why_bad}
              {explanation.followup_line.length > 0 && (
                <MoveLine
                  label="Consequence line"
                  moves={explanation.followup_line}
                  color="red"
                />
              )}
            </Section>
          )}

          {/* Better alternative */}
          {explanation.better_move_san && (
            <Section label={`Better: ${explanation.better_move_san}`} accent="green">
              {explanation.better_move_explanation}
              {explanation.best_followup_line.length > 0 && (
                <MoveLine
                  label="After the better move"
                  moves={explanation.best_followup_line}
                  color="green"
                />
              )}
            </Section>
          )}
        </div>
      )}
    </div>
  )
}

// ── Sub-components ────────────────────────────────────────────────────────────

function Section({
  label,
  accent,
  children,
}: {
  label: string
  accent?: 'red' | 'green'
  children: React.ReactNode
}) {
  const border = accent === 'red'
    ? 'border-red-800/60 bg-red-500/5'
    : accent === 'green'
    ? 'border-green-800/60 bg-green-500/5'
    : 'border-gray-700 bg-gray-800/40'

  const labelColor = accent === 'red'
    ? 'text-red-400'
    : accent === 'green'
    ? 'text-green-400'
    : 'text-gray-400'

  return (
    <div className={`rounded-md border p-3 space-y-2 ${border}`}>
      <p className={`text-xs font-semibold uppercase tracking-wide ${labelColor}`}>{label}</p>
      <div className="text-gray-300 leading-relaxed">{children}</div>
    </div>
  )
}

function MoveLine({
  label,
  moves,
  color,
}: {
  label: string
  moves: string[]
  color: 'red' | 'green'
}) {
  const dotColor = color === 'red' ? 'bg-red-500' : 'bg-green-500'
  return (
    <div className="mt-2 flex items-center gap-2 flex-wrap">
      <span className="text-xs text-gray-500">{label}:</span>
      {moves.map((m, i) => (
        <span key={i} className="flex items-center gap-1">
          <span className={`w-1.5 h-1.5 rounded-full ${dotColor} opacity-60`} />
          <span className="font-mono text-xs text-gray-300">{m}</span>
        </span>
      ))}
    </div>
  )
}
