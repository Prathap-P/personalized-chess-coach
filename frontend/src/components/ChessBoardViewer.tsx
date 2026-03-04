import { useState, useCallback, useMemo } from 'react'
import { Chessboard } from 'react-chessboard'
import { Chess } from 'chess.js'
import type { MoveAnalysis } from '../types/analysis'
import clsx from 'clsx'

const CLASSIFICATION_COLORS: Record<string, string> = {
  brilliant:  'bg-purple-500/20 text-purple-300 border-purple-700',
  great:      'bg-cyan-500/20 text-cyan-300 border-cyan-700',
  best:       'bg-green-500/20 text-green-300 border-green-700',
  excellent:  'bg-green-500/10 text-green-400 border-green-800',
  good:       'bg-gray-700/40 text-gray-300 border-gray-700',
  inaccuracy: 'bg-yellow-500/20 text-yellow-300 border-yellow-700',
  mistake:    'bg-orange-500/20 text-orange-300 border-orange-700',
  blunder:    'bg-red-500/20 text-red-300 border-red-700',
  forced:     'bg-gray-700/20 text-gray-500 border-gray-800',
}

const CLASSIFICATION_EMOJI: Record<string, string> = {
  brilliant: '✨', great: '🎯', best: '⭐', excellent: '👍',
  good: '✅', inaccuracy: '⚠️', mistake: '❌', blunder: '💥', forced: '🔒',
}

interface Props {
  /**
   * Pre-computed FEN array: index 0 = starting position, index N = after move N.
   * Comes from parsePgnPreview() so it's available before analysis completes.
   */
  fens: string[]
  /**
   * SAN move list matching fens (fens[i+1] is the position after moveSans[i]).
   * Used to label the move list when no move analysis is available yet.
   */
  moveSans: string[]
  /**
   * Per-move analysis from the backend. When provided, the move list shows
   * classification badges and accuracy. Optional — works without it (preview mode).
   */
  moves?: MoveAnalysis[]
  /**
   * When true the board is draggable and users can explore variations freely.
   * A "Reset to game" button appears to go back to the game position.
   */
  interactive?: boolean
}

export default function ChessBoardViewer({ fens, moveSans, moves, interactive = false }: Props) {
  const [currentIdx, setCurrentIdx] = useState(0)
  // Exploration state: when the user drags pieces we diverge from the game FENs
  const [explorationFen, setExplorationFen] = useState<string | null>(null)
  const [explorationGame, setExplorationGame] = useState<Chess | null>(null)

  const goTo = useCallback(
    (idx: number) => {
      const clamped = Math.max(0, Math.min(idx, fens.length - 1))
      setCurrentIdx(clamped)
      setExplorationFen(null)
      setExplorationGame(null)
    },
    [fens.length],
  )

  const resetExploration = () => {
    setExplorationFen(null)
    setExplorationGame(null)
  }

  // While in exploration mode the board shows the user's position, not the game
  const displayFen = explorationFen ?? fens[currentIdx]
  const currentMove = moves && currentIdx > 0 ? moves[currentIdx - 1] : null

  // Arrow highlighting for best move / blunder on the current position
  const arrows = useMemo(() => {
    if (!currentMove || explorationFen) return []
    if (currentMove.is_blunder || currentMove.is_mistake) {
      return [[currentMove.move_uci.slice(0, 2), currentMove.move_uci.slice(2, 4), 'red']]
    }
    return []
  }, [currentMove, explorationFen])

  function onPieceDrop(sourceSquare: string, targetSquare: string): boolean {
    if (!interactive) return false
    const game = explorationGame ?? new Chess(fens[currentIdx])
    const result = game.move({ from: sourceSquare, to: targetSquare, promotion: 'q' })
    if (!result) return false
    setExplorationGame(new Chess(game.fen()))
    setExplorationFen(game.fen())
    return true
  }

  return (
    <div className="flex flex-col lg:flex-row gap-6">
      {/* Board column */}
      <div className="flex-shrink-0">
        <div className="w-full max-w-sm mx-auto lg:mx-0 relative">
          {explorationFen && (
            <div className="absolute top-1 left-1 z-10">
              <span className="text-xs bg-yellow-500/20 text-yellow-300 border border-yellow-700 rounded px-2 py-0.5">
                Exploring
              </span>
            </div>
          )}
          <Chessboard
            position={displayFen}
            arePiecesDraggable={interactive}
            onPieceDrop={onPieceDrop}
            boardWidth={340}
            // @ts-ignore — customArrows is valid in react-chessboard v4
            customArrows={arrows}
          />
        </div>

        {/* Navigation */}
        <div className="flex justify-center gap-2 mt-3">
          {[
            { label: '⏮', fn: () => goTo(0) },
            { label: '◀', fn: () => goTo(currentIdx - 1) },
            { label: '▶', fn: () => goTo(currentIdx + 1) },
            { label: '⏭', fn: () => goTo(fens.length - 1) },
          ].map(({ label, fn }) => (
            <button key={label} onClick={fn} className="btn-secondary px-3 py-1 text-sm">
              {label}
            </button>
          ))}
          {explorationFen && (
            <button onClick={resetExploration} className="btn-secondary px-3 py-1 text-sm text-yellow-300">
              ↩ Reset
            </button>
          )}
        </div>

        {/* Current move info (only in analyzed mode) */}
        {currentMove && (
          <div
            className={clsx(
              'mt-3 p-3 rounded-lg border text-sm',
              CLASSIFICATION_COLORS[currentMove.classification] ?? '',
            )}
          >
            <div className="flex items-center justify-between mb-1">
              <span className="font-bold">
                {currentMove.move_number}. {currentMove.move_san}
              </span>
              <span className="capitalize text-xs">
                {CLASSIFICATION_EMOJI[currentMove.classification]}{' '}
                {currentMove.classification}
              </span>
            </div>
            <div className="text-xs opacity-70">
              Accuracy: {currentMove.move_accuracy.toFixed(1)}% · Loss: {currentMove.eval_loss.toFixed(0)} cp
            </div>
            {currentMove.comment && (
              <div className="mt-1 text-xs opacity-80">{currentMove.comment}</div>
            )}
          </div>
        )}

        {/* Preview-mode position indicator (no analysis yet) */}
        {!currentMove && currentIdx > 0 && moveSans[currentIdx - 1] && (
          <div className="mt-3 p-3 rounded-lg border border-gray-700 bg-gray-800/40 text-sm">
            <span className="text-gray-400">Move {currentIdx}: </span>
            <span className="font-mono text-gray-200">{moveSans[currentIdx - 1]}</span>
          </div>
        )}
      </div>

      {/* Move list */}
      <div className="flex-1 overflow-y-auto max-h-[420px] pr-1">
        <div className="grid grid-cols-2 gap-1 text-xs">
          {moveSans.map((san, i) => {
            const idx = i + 1
            const isActive = currentIdx === idx && !explorationFen
            const move = moves?.[i]
            return (
              <button
                key={i}
                onClick={() => goTo(idx)}
                className={clsx(
                  'text-left px-2 py-1.5 rounded transition-colors border',
                  isActive
                    ? (move ? CLASSIFICATION_COLORS[move.classification] : 'bg-gray-700 border-gray-600')
                    : 'border-transparent hover:bg-gray-800/60',
                )}
              >
                <span className="text-gray-500 mr-1">
                  {i % 2 === 0 ? `${Math.floor(i / 2) + 1}.` : '...'}
                </span>
                <span className={isActive ? '' : 'text-gray-300'}>{san}</span>
                {move && (move.is_blunder || move.is_mistake || move.is_inaccuracy) && (
                  <span className="ml-1">{CLASSIFICATION_EMOJI[move.classification]}</span>
                )}
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}
