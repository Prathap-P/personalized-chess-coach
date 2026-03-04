import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../store/authStore'
import { useAnalysisStream } from '../hooks/useWebSocket'
import { prefetchPgn } from '../services/api'
import { parsePgnPreview } from '../utils/pgnPreview'
import type { PgnPreview } from '../utils/pgnPreview'
import ProgressBar from '../components/ProgressBar'
import ClassificationTable from '../components/ClassificationTable'
import CoachingReport from '../components/CoachingReport'
import ChessBoardViewer from '../components/ChessBoardViewer'
import GamePreviewPanel from '../components/GamePreviewPanel'
import type { GameAnalysis } from '../types/analysis'

export default function GamePage() {
  const navigate = useNavigate()
  const { isAuthenticated } = useAuthStore()

  const [pgn, setPgn] = useState('')
  const [gameUrl, setGameUrl] = useState('')
  const [playerName, setPlayerName] = useState('')
  const [depth, setDepth] = useState(18)
  const [includeLlm, setIncludeLlm] = useState(true)
  const [inputMode, setInputMode] = useState<'pgn' | 'url'>('pgn')

  // Preview: parsed immediately from PGN text (or after URL fetch), before analysis
  const [preview, setPreview] = useState<PgnPreview | null>(null)
  const [urlFetching, setUrlFetching] = useState(false)
  const [urlFetchError, setUrlFetchError] = useState<string | null>(null)
  // Track the source label for the preview panel badge
  const [previewSource, setPreviewSource] = useState<string>('PGN')

  const urlDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const { status, progress, result, error, run, reset } =
    useAnalysisStream<GameAnalysis>()

  // Parse PGN preview immediately as user types
  useEffect(() => {
    if (inputMode !== 'pgn') return
    if (!pgn.trim()) {
      setPreview(null)
      return
    }
    const p = parsePgnPreview(pgn)
    setPreview(p.valid ? p : null)
    setPreviewSource('PGN')
  }, [pgn, inputMode])

  // Auto-fetch PGN when a valid chess.com / lichess URL is pasted
  useEffect(() => {
    if (inputMode !== 'url') return
    if (urlDebounceRef.current) clearTimeout(urlDebounceRef.current)
    setUrlFetchError(null)

    const trimmed = gameUrl.trim()
    const isChessUrl =
      trimmed.startsWith('http') &&
      (trimmed.includes('chess.com') || trimmed.includes('lichess.org'))

    if (!isChessUrl) {
      setPreview(null)
      return
    }

    // Debounce 600 ms to avoid firing on every keypress
    urlDebounceRef.current = setTimeout(async () => {
      setUrlFetching(true)
      try {
        const fetchedPgn = await prefetchPgn(trimmed)
        const p = parsePgnPreview(fetchedPgn)
        setPreview(p.valid ? p : null)
        const source = trimmed.includes('lichess.org') ? 'lichess' : 'chess.com'
        setPreviewSource(source)
      } catch (err) {
        setUrlFetchError(err instanceof Error ? err.message : 'Failed to fetch game')
        setPreview(null)
      } finally {
        setUrlFetching(false)
      }
    }, 600)

    return () => {
      if (urlDebounceRef.current) clearTimeout(urlDebounceRef.current)
    }
  }, [gameUrl, inputMode])

  if (!isAuthenticated()) {
    return (
      <div className="card text-center space-y-4">
        <p className="text-gray-400">You must be logged in to analyze games.</p>
        <button onClick={() => navigate('/')} className="btn-primary">
          Go to Login
        </button>
      </div>
    )
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    reset()
    const data = inputMode === 'pgn' ? pgn : gameUrl
    run({
      type: 'game',
      payload: {
        data,
        player: playerName || undefined,
        options: { depth, include_llm: includeLlm },
      },
    })
  }

  function handleReset() {
    reset()
    // Keep the preview — user can re-analyze the same game
  }

  const isRunning = status === 'connecting' || status === 'running'

  // The FEN/SAN arrays come from the preview (client-parsed) so they're always
  // available; the moves array from the result adds classification overlay
  const INITIAL_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'
  const boardFens = preview?.fens ?? [INITIAL_FEN]
  const boardSans = preview?.moveSans ?? []

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-xl font-bold">Game Analysis</h1>
        <p className="text-gray-500 text-sm mt-1">Analyze a chess game with Stockfish + AI coaching</p>
      </div>

      {/* Input form */}
      <form onSubmit={handleSubmit} className="card space-y-4">
        {/* Mode toggle */}
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => { setInputMode('pgn'); setPreview(null) }}
            className={inputMode === 'pgn' ? 'btn-primary text-sm px-3 py-1' : 'btn-secondary text-sm px-3 py-1'}
          >
            Paste PGN
          </button>
          <button
            type="button"
            onClick={() => { setInputMode('url'); setPreview(null) }}
            className={inputMode === 'url' ? 'btn-primary text-sm px-3 py-1' : 'btn-secondary text-sm px-3 py-1'}
          >
            Game URL
          </button>
        </div>

        {inputMode === 'pgn' ? (
          <div>
            <label className="label">PGN</label>
            <textarea
              className="input font-mono text-xs"
              rows={8}
              value={pgn}
              onChange={(e) => setPgn(e.target.value)}
              placeholder={'[Event "..."]\n[White "Player1"]\n[Black "Player2"]\n...'}
            />
          </div>
        ) : (
          <div>
            <label className="label">Game URL (chess.com or lichess)</label>
            <div className="relative">
              <input
                className="input pr-10"
                value={gameUrl}
                onChange={(e) => setGameUrl(e.target.value)}
                placeholder="https://www.chess.com/game/live/..."
              />
              {urlFetching && (
                <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-500 animate-pulse">
                  Fetching…
                </span>
              )}
            </div>
            {urlFetchError && (
              <p className="text-xs text-red-400 mt-1">{urlFetchError}</p>
            )}
          </div>
        )}

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="label">Player Name (for stats)</label>
            <input
              className="input"
              value={playerName}
              onChange={(e) => setPlayerName(e.target.value)}
              placeholder="Optional"
            />
          </div>
          <div>
            <label className="label">Analysis Depth</label>
            <input
              className="input"
              type="number"
              min={8}
              max={30}
              value={depth}
              onChange={(e) => setDepth(Number(e.target.value))}
            />
          </div>
        </div>

        <div className="flex items-center gap-2">
          <input
            id="llm-toggle"
            type="checkbox"
            checked={includeLlm}
            onChange={(e) => setIncludeLlm(e.target.checked)}
            className="w-4 h-4 accent-brand-500"
          />
          <label htmlFor="llm-toggle" className="text-sm text-gray-300">
            Include AI coaching feedback
          </label>
        </div>

        <div className="flex gap-3">
          <button
            type="submit"
            disabled={isRunning || (!pgn && !gameUrl) || urlFetching}
            className="btn-primary"
          >
            {isRunning ? 'Analyzing…' : 'Analyze Game'}
          </button>
          {status !== 'idle' && (
            <button type="button" onClick={handleReset} className="btn-secondary">
              Reset
            </button>
          )}
        </div>
      </form>

      {/* Progress */}
      {isRunning && <ProgressBar progress={progress} label="Analyzing moves…" />}

      {/* Error */}
      {error && (
        <div className="card border-red-800 bg-red-500/10 text-red-400 text-sm">
          {error}
        </div>
      )}

      {/* ── Preview / Results ─────────────────────────────────────────────── */}
      {preview && (
        <div className="space-y-4">
          {/* Always show game info panel */}
          <GamePreviewPanel
            metadata={result?.metadata ?? preview.metadata}
            source={previewSource}
          />

          {/* Show classification table only after analysis */}
          {result && (
            <ClassificationTable
              whiteName={result.metadata.white_player}
              blackName={result.metadata.black_player}
              whiteStats={result.white_stats}
              blackStats={result.black_stats}
            />
          )}

          {/* Board: preview mode before analysis, analyzed mode after */}
          <div className="card">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-gray-400">
                {result ? 'Game Review' : 'Preview'}
              </h2>
              {!result && (
                <span className="text-xs text-gray-600">
                  Navigate the board while analysis runs
                </span>
              )}
            </div>
            <ChessBoardViewer
              fens={result ? preview.fens : boardFens}
              moveSans={result ? preview.moveSans : boardSans}
              moves={result?.moves}
              interactive={!isRunning}
            />
          </div>

          {/* AI coaching report */}
          {result?.ai_summary && (
            <CoachingReport
              summary={result.ai_summary}
              strengths={result.ai_strengths}
              weaknesses={result.ai_weaknesses}
              recommendations={result.ai_recommendations}
            />
          )}
        </div>
      )}
    </div>
  )
}
