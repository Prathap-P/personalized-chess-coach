import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { login, getHealth } from '../services/api'
import { useAuthStore } from '../store/authStore'
import type { HealthStatus } from '../types/analysis'

export default function HomePage() {
  const navigate = useNavigate()
  const { setAuth, isAuthenticated, username } = useAuthStore()

  const [baseUrl, setBaseUrl] = useState(
    () => localStorage.getItem('api_base_url') || 'http://localhost:8000',
  )
  const [un, setUn] = useState('')
  const [pw, setPw] = useState('')
  const [health, setHealth] = useState<HealthStatus | null>(null)
  const [healthError, setHealthError] = useState<string | null>(null)
  const [loginError, setLoginError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  function saveUrl() {
    localStorage.setItem('api_base_url', baseUrl)
  }

  async function testConnection() {
    saveUrl()
    setHealth(null)
    setHealthError(null)
    setLoading(true)
    try {
      const h = await getHealth()
      setHealth(h)
    } catch (err) {
      setHealthError(err instanceof Error ? err.message : 'Connection failed')
    } finally {
      setLoading(false)
    }
  }

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault()
    saveUrl()
    setLoginError(null)
    setLoading(true)
    try {
      const token = await login(un, pw)
      setAuth(token, un)
    } catch (err) {
      setLoginError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  if (isAuthenticated()) {
    return (
      <div className="max-w-2xl mx-auto space-y-6">
        <div className="card text-center space-y-3">
          <div className="text-5xl">♟</div>
          <h1 className="text-2xl font-bold">Chess Coach</h1>
          <p className="text-gray-400">
            Welcome back, <span className="text-brand-400">{username}</span>
          </p>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <button onClick={() => navigate('/game')} className="card hover:border-brand-700 transition-colors text-center space-y-2 cursor-pointer">
            <div className="text-3xl">🔍</div>
            <div className="font-semibold">Analyze Game</div>
            <div className="text-sm text-gray-500">Paste a PGN or game URL</div>
          </button>
          <button onClick={() => navigate('/profile')} className="card hover:border-brand-700 transition-colors text-center space-y-2 cursor-pointer">
            <div className="text-3xl">📊</div>
            <div className="font-semibold">Profile Analysis</div>
            <div className="text-sm text-gray-500">Analyze your recent games</div>
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-md mx-auto space-y-6">
      <div className="text-center space-y-2">
        <div className="text-5xl">♟</div>
        <h1 className="text-2xl font-bold">Chess Coach</h1>
        <p className="text-gray-400 text-sm">Connect to your local Chess Coach server</p>
      </div>

      {/* Server URL */}
      <div className="card space-y-4">
        <h2 className="font-semibold">Server Configuration</h2>
        <div>
          <label className="label">API Server URL</label>
          <input
            className="input"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder="http://localhost:8000"
          />
        </div>
        <button onClick={testConnection} disabled={loading} className="btn-secondary w-full">
          {loading ? 'Testing…' : 'Test Connection'}
        </button>

        {health && (
          <div className="text-sm space-y-1 p-3 bg-gray-800/50 rounded-lg">
            <div className="flex justify-between">
              <span className="text-gray-400">Status</span>
              <span className="text-green-400 font-medium">✅ {health.status}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">Stockfish</span>
              <span className={health.stockfish === 'ok' ? 'text-green-400' : 'text-red-400'}>
                {health.stockfish === 'ok' ? '✅ ok' : '❌ ' + health.stockfish}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">LLM</span>
              <span className={health.llm_configured ? 'text-green-400' : 'text-yellow-400'}>
                {health.llm_configured ? `✅ ${health.llm_model}` : '⚠️ not configured'}
              </span>
            </div>
          </div>
        )}

        {healthError && (
          <div className="text-sm text-red-400 bg-red-500/10 border border-red-800 rounded-lg p-3">
            {healthError}
          </div>
        )}
      </div>

      {/* Login */}
      <form onSubmit={handleLogin} className="card space-y-4">
        <h2 className="font-semibold">Login</h2>
        <div>
          <label className="label">Username</label>
          <input className="input" value={un} onChange={(e) => setUn(e.target.value)} placeholder="admin" />
        </div>
        <div>
          <label className="label">Password</label>
          <input className="input" type="password" value={pw} onChange={(e) => setPw(e.target.value)} placeholder="••••••••" />
        </div>
        {loginError && (
          <div className="text-sm text-red-400 bg-red-500/10 border border-red-800 rounded-lg p-3">
            {loginError}
          </div>
        )}
        <button type="submit" disabled={loading || !un || !pw} className="btn-primary w-full">
          {loading ? 'Logging in…' : 'Login'}
        </button>
        <p className="text-xs text-gray-600 text-center">
          Run <code className="text-gray-400">chess-coach api-setup</code> to create credentials
        </p>
      </form>
    </div>
  )
}
