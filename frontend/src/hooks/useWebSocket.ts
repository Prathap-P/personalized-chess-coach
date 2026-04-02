import { useCallback, useRef, useState } from 'react'
import type { WsProgressMessage, MoveExplanation } from '../types/analysis'
import { useAuthStore } from '../store/authStore'
import { getBaseUrl } from '../services/api'

type Status = 'idle' | 'connecting' | 'running' | 'done' | 'error'

interface UseWebSocketReturn<T> {
  status: Status
  progress: WsProgressMessage | null
  result: T | null
  error: string | null
  run: (request: object) => void
  /** Send any message on the open socket (for move_analysis requests) */
  sendMessage: (msg: object) => void
  reset: () => void
}

export interface MoveAnalysisCallbacks {
  onExplanationDone: (move_san: string, data: MoveExplanation) => void
  onExplanationError: (move_san: string, message: string) => void
}

export function useAnalysisStream<T = unknown>(
  moveCallbacks?: MoveAnalysisCallbacks,
): UseWebSocketReturn<T> {
  const token = useAuthStore((s) => s.token)
  const wsRef = useRef<WebSocket | null>(null)
  // Use a ref so onclose/onerror always read the current status value
  const statusRef = useRef<Status>('idle')

  const [status, setStatus] = useState<Status>('idle')
  const [progress, setProgress] = useState<WsProgressMessage | null>(null)
  const [result, setResult] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)

  const _setStatus = useCallback((s: Status) => {
    statusRef.current = s
    setStatus(s)
  }, [])

  const reset = useCallback(() => {
    wsRef.current?.close()
    wsRef.current = null
    _setStatus('idle')
    setProgress(null)
    setResult(null)
    setError(null)
  }, [_setStatus])

  const sendMessage = useCallback((msg: object) => {
    const ws = wsRef.current
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(msg))
    }
  }, [])

  const run = useCallback(
    (request: object) => {
      reset()
      if (!token) {
        setError('Not authenticated. Please log in first.')
        _setStatus('error')
        return
      }

      const base = getBaseUrl().replace(/^http/, 'ws')
      const ws = new WebSocket(`${base}/api/v1/analyze/stream`)
      wsRef.current = ws
      _setStatus('connecting')

      ws.onopen = () => {
        // Step 1: send auth token
        ws.send(JSON.stringify({ token }))
        // Step 2: send analysis request after 250 ms to let server validate auth
        setTimeout(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify(request))
          }
        }, 250)
      }

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      ws.onmessage = (event: MessageEvent) => {
        const msg = JSON.parse(event.data as string) as any

        // Server keepalive — silently ignore
        if (msg.type === 'ping') return

        if (msg.type === 'progress') {
          _setStatus('running')
          setProgress(msg as WsProgressMessage)
        } else if (msg.type === 'result') {
          setResult(msg.analysis as T)
          _setStatus('done')
          // Keep socket open — user may send move_analysis requests
        } else if (msg.type === 'error') {
          setError(msg.message as string)
          _setStatus('error')
        } else if (msg.type === 'move_explanation_done') {
          moveCallbacks?.onExplanationDone(msg.move_san, msg.data as MoveExplanation)
        } else if (msg.type === 'move_explanation_error') {
          moveCallbacks?.onExplanationError(msg.move_san, msg.message)
        }
      }

      ws.onerror = () => {
        setError('WebSocket connection failed. Is the server running?')
        _setStatus('error')
      }

      ws.onclose = () => {
        // Only flag as unexpected if analysis was still in-flight
        const s = statusRef.current
        if (s === 'connecting' || s === 'running') {
          setError('Connection lost — server may still be processing. Check server logs.')
          _setStatus('error')
        }
      }
    },
    [token, reset, _setStatus],
  )

  return { status, progress, result, error, run, sendMessage, reset }
}
