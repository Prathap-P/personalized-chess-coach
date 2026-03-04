/**
 * GamePreviewPanel
 *
 * Shows player names, ratings, event, date, result, and opening name as soon
 * as a PGN is parsed on the client — before any backend analysis runs.
 */

import type { GameMetadata } from '../types/analysis'
import clsx from 'clsx'

interface Props {
  metadata: GameMetadata
  /** Optional source badge label (e.g. "chess.com", "lichess", "PGN") */
  source?: string
}

function resultLabel(result: string): { text: string; cls: string } {
  if (result === '1-0') return { text: 'White wins', cls: 'text-green-400' }
  if (result === '0-1') return { text: 'Black wins', cls: 'text-green-400' }
  if (result === '1/2-1/2') return { text: 'Draw', cls: 'text-yellow-400' }
  return { text: result || '*', cls: 'text-gray-400' }
}

export default function GamePreviewPanel({ metadata, source }: Props) {
  const res = resultLabel(metadata.result)

  return (
    <div className="card space-y-3">
      <div className="flex items-start justify-between gap-4">
        {/* Players */}
        <div className="flex-1 space-y-1">
          <PlayerRow
            name={metadata.white_player}
            elo={metadata.white_elo}
            color="white"
          />
          <div className="text-xs text-gray-600 pl-6">vs</div>
          <PlayerRow
            name={metadata.black_player}
            elo={metadata.black_elo}
            color="black"
          />
        </div>

        {/* Result + source */}
        <div className="text-right space-y-1 shrink-0">
          <div className={clsx('text-sm font-semibold', res.cls)}>
            {metadata.result}
            <span className="text-xs font-normal ml-1 text-gray-500">{res.text}</span>
          </div>
          {source && (
            <span className="inline-block text-xs px-2 py-0.5 rounded bg-gray-800 text-gray-400 border border-gray-700">
              {source}
            </span>
          )}
        </div>
      </div>

      {/* Game details */}
      <div className="border-t border-gray-800 pt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500">
        {metadata.opening && (
          <span>
            <span className="text-gray-600">Opening: </span>
            <span className="text-gray-400">
              {metadata.eco ? `[${metadata.eco}] ` : ''}
              {metadata.opening}
            </span>
          </span>
        )}
        {metadata.event && metadata.event !== '?' && (
          <span>
            <span className="text-gray-600">Event: </span>
            <span className="text-gray-400">{metadata.event}</span>
          </span>
        )}
        {metadata.date && (
          <span>
            <span className="text-gray-600">Date: </span>
            <span className="text-gray-400">{metadata.date.replace(/\.\?\?/g, '')}</span>
          </span>
        )}
      </div>
    </div>
  )
}

function PlayerRow({
  name,
  elo,
  color,
}: {
  name: string
  elo: number | null
  color: 'white' | 'black'
}) {
  return (
    <div className="flex items-center gap-2">
      {/* Piece icon */}
      <span
        className={clsx(
          'w-4 h-4 rounded-full border flex-shrink-0 text-center leading-none text-xs',
          color === 'white'
            ? 'bg-white border-gray-400 text-gray-900'
            : 'bg-gray-900 border-gray-500 text-white',
        )}
        aria-label={color}
      >
        ♟
      </span>
      <span className="font-medium text-sm text-gray-200">{name || '?'}</span>
      {elo && <span className="text-xs text-gray-500">({elo})</span>}
    </div>
  )
}
