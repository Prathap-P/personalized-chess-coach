/**
 * Hook for on-demand per-move analysis over the existing WebSocket connection.
 *
 * Usage:
 *   const { explanation, loading, error, analyse } = useMoveAnalysis(sendWsMessage)
 *
 *   // When user navigates to a move:
 *   analyse({ fen, move_san, move_uci, recent_moves, mode: 'pgn' })
 *
 *   // Pre-fetch next moves in background:
 *   prefetch([{ fen, move_san, move_uci, recent_moves }])
 */

import { useCallback, useRef, useState } from 'react'
import type { MoveExplanation } from '../types/analysis'

export interface MoveAnalysisRequest {
  fen: string
  move_san: string
  move_uci: string
  recent_moves?: string[]
  mode?: 'pgn' | 'interactive'
}

interface UseMoveAnalysisReturn {
  /** Explanation for the currently active move (null while loading or idle) */
  explanation: MoveExplanation | null
  loading: boolean
  error: string | null
  /** The move SAN most recently requested (even while still loading) */
  currentMoveSan: string
  /** Trigger analysis for a move — cancels any in-progress request */
  analyse: (req: MoveAnalysisRequest) => void
  /** Pre-fetch explanations for upcoming moves (fire-and-forget) */
  prefetch: (reqs: MoveAnalysisRequest[]) => void
  /** Called by the parent WS handler when a move_explanation_done message arrives */
  onExplanationDone: (move_san: string, data: MoveExplanation) => void
  /** Called by the parent WS handler when a move_explanation_error message arrives */
  onExplanationError: (move_san: string, message: string) => void
}

const LRU_MAX = 50

export function useMoveAnalysis(
  sendWsMessage: (msg: object) => void,
): UseMoveAnalysisReturn {
  const [explanation, setExplanation] = useState<MoveExplanation | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [currentMoveSan, setCurrentMoveSan] = useState<string>('')

  // LRU in-memory cache: move_san → MoveExplanation
  // Using a Map preserves insertion order for eviction
  const cache = useRef<Map<string, MoveExplanation>>(new Map())
  // Track which move_san we're currently waiting for (to ignore stale responses)
  const pending = useRef<string | null>(null)

  const _cacheKey = (req: MoveAnalysisRequest) =>
    `${req.fen.split(' ').slice(0, 4).join(' ')}|${req.move_san}`

  const _addToCache = (key: string, data: MoveExplanation) => {
    if (cache.current.has(key)) {
      cache.current.delete(key) // refresh position
    }
    cache.current.set(key, data)
    // Evict oldest if over limit
    if (cache.current.size > LRU_MAX) {
      const oldest = cache.current.keys().next().value
      if (oldest) cache.current.delete(oldest)
    }
  }

  const analyse = useCallback(
    (req: MoveAnalysisRequest) => {
      const key = _cacheKey(req)

      // Instant cache hit — no WS round-trip
      const cached = cache.current.get(key)
      if (cached) {
        setExplanation(cached)
        setLoading(false)
        setError(null)
        pending.current = null
        return
      }

      // Mark as pending and request from server
      pending.current = req.move_san
      setCurrentMoveSan(req.move_san)
      setLoading(true)
      setError(null)
      setExplanation(null)

      sendWsMessage({
        type: 'move_analysis',
        payload: {
          fen: req.fen,
          move_san: req.move_san,
          move_uci: req.move_uci,
          recent_moves: req.recent_moves ?? [],
          mode: req.mode ?? 'pgn',
        },
      })
    },
    [sendWsMessage],
  )

  const prefetch = useCallback(
    (reqs: MoveAnalysisRequest[]) => {
      for (const req of reqs.slice(0, 2)) {
        const key = _cacheKey(req)
        if (cache.current.has(key)) continue // already cached
        // Send silently — we don't update loading state for pre-fetches
        sendWsMessage({
          type: 'move_analysis',
          payload: {
            fen: req.fen,
            move_san: req.move_san,
            move_uci: req.move_uci,
            recent_moves: req.recent_moves ?? [],
            mode: req.mode ?? 'pgn',
          },
        })
      }
    },
    [sendWsMessage],
  )

  const onExplanationDone = useCallback(
    (move_san: string, data: MoveExplanation) => {
      // Use the norm_fen from the server response to build the correct compound key
      const key = data.norm_fen ? `${data.norm_fen}|${move_san}` : move_san
      _addToCache(key, data)

      // Only update displayed explanation if this is the move we're waiting for
      if (pending.current === move_san) {
        setExplanation(data)
        setLoading(false)
        setError(null)
        pending.current = null
      }
    },
    [],
  )

  const onExplanationError = useCallback(
    (move_san: string, message: string) => {
      if (pending.current === move_san) {
        setError(message)
        setLoading(false)
        pending.current = null
      }
    },
    [],
  )

  return { explanation, loading, error, currentMoveSan, analyse, prefetch, onExplanationDone, onExplanationError }
}
