import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../store/authStore'
import { useAnalysisStream } from '../hooks/useWebSocket'
import ProgressBar from '../components/ProgressBar'
import ProfileCharts from '../components/ProfileCharts'
import type { ProfileAnalysis } from '../types/analysis'

export default function ProfilePage() {
  const navigate = useNavigate()
  const { isAuthenticated } = useAuthStore()

  const [username, setUsername] = useState('')
  const [platform, setPlatform] = useState<'chess.com' | 'lichess'>('chess.com')
  const [numGames, setNumGames] = useState(20)
  const [color, setColor] = useState<'white' | 'black' | 'both'>('both')
  const [depth, setDepth] = useState(18)
  const [includeLlm, setIncludeLlm] = useState(true)

  const { status, progress, result, error, run, reset } =
    useAnalysisStream<ProfileAnalysis>()

  if (!isAuthenticated()) {
    return (
      <div className="card text-center space-y-4">
        <p className="text-gray-400">You must be logged in to analyze profiles.</p>
        <button onClick={() => navigate('/')} className="btn-primary">
          Go to Login
        </button>
      </div>
    )
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    reset()
    // Format request to match backend WS protocol
    run({
      type: 'profile',
      payload: {
        username,
        platform,
        num_games: numGames,
        color: color === 'both' ? null : color,
        options: {
          depth,
          include_coaching: includeLlm,
        },
      },
    })
  }

  const isRunning = status === 'connecting' || status === 'running'

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-xl font-bold">Profile Analysis</h1>
        <p className="text-gray-500 text-sm mt-1">
          Analyze your recent games and discover patterns in your play
        </p>
      </div>

      {/* Input form */}
      <form onSubmit={handleSubmit} className="card space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="label">Username</label>
            <input
              className="input"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="your_username"
              required
            />
          </div>
          <div>
            <label className="label">Platform</label>
            <select
              className="input"
              value={platform}
              onChange={(e) => setPlatform(e.target.value as 'chess.com' | 'lichess')}
            >
              <option value="chess.com">Chess.com</option>
              <option value="lichess">Lichess</option>
            </select>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-4">
          <div>
            <label className="label">Games to Analyze</label>
            <input
              className="input"
              type="number"
              min={1}
              max={100}
              value={numGames}
              onChange={(e) => setNumGames(Number(e.target.value))}
            />
          </div>
          <div>
            <label className="label">Color</label>
            <select
              className="input"
              value={color}
              onChange={(e) => setColor(e.target.value as 'white' | 'black' | 'both')}
            >
              <option value="both">Both</option>
              <option value="white">White</option>
              <option value="black">Black</option>
            </select>
          </div>
          <div>
            <label className="label">Depth</label>
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
          <button type="submit" disabled={isRunning || !username} className="btn-primary">
            {isRunning ? 'Analyzing…' : 'Analyze Profile'}
          </button>
          {status !== 'idle' && (
            <button type="button" onClick={reset} className="btn-secondary">
              Reset
            </button>
          )}
        </div>
      </form>

      {/* Progress */}
      {(status === 'connecting' || status === 'running') && (
        <ProgressBar progress={progress} label={`Analyzing games for ${username}…`} />
      )}

      {/* Error */}
      {error && (
        <div className="card border-red-800 bg-red-500/10 text-red-400 text-sm">
          {error}
        </div>
      )}

      {/* Results */}
      {result && <ProfileCharts profile={result} />}
    </div>
  )
}
