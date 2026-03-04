import axios, { AxiosError } from 'axios'
import type { Config, GameAnalysis, HealthStatus, ProfileAnalysis } from '../types/analysis'
import { useAuthStore } from '../store/authStore'

// Base URL is configurable (user stores it in localStorage via Settings page)
export function getBaseUrl(): string {
  return localStorage.getItem('api_base_url') || 'http://localhost:8000'
}

function apiClient() {
  const token = useAuthStore.getState().token
  return axios.create({
    baseURL: getBaseUrl(),
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
}

function handleError(err: unknown): never {
  if (err instanceof AxiosError) {
    const msg = err.response?.data?.detail ?? err.message
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg))
  }
  throw err
}

// ── Auth ──────────────────────────────────────────────────────────────────────

export async function login(username: string, password: string): Promise<string> {
  try {
    const res = await axios.post(`${getBaseUrl()}/auth/token`, { username, password })
    return res.data.access_token as string
  } catch (err) {
    handleError(err)
  }
}

// ── PGN Prefetch (no auth required) ──────────────────────────────────────────

/**
 * Download PGN for a chess.com or lichess URL without running analysis.
 * Used to show the board preview immediately after a URL is pasted.
 */
export async function prefetchPgn(url: string): Promise<string> {
  try {
    const res = await axios.get(`${getBaseUrl()}/api/v1/analyze/prefetch`, {
      params: { url },
    })
    return (res.data as { pgn: string }).pgn
  } catch (err) {
    handleError(err)
  }
}

// ── Health ────────────────────────────────────────────────────────────────────

export async function getHealth(): Promise<HealthStatus> {
  try {
    const res = await axios.get(`${getBaseUrl()}/health`)
    return res.data as HealthStatus
  } catch (err) {
    handleError(err)
  }
}

// ── Analysis ──────────────────────────────────────────────────────────────────

export interface AnalyzeGameOptions {
  data: string            // URL or PGN text
  player?: string
  depth?: number
  include_llm?: boolean
  skill_level?: number
}

export async function analyzeGame(opts: AnalyzeGameOptions): Promise<GameAnalysis> {
  try {
    const res = await apiClient().post('/api/v1/analyze/game', {
      source: opts.data.startsWith('http') ? 'url' : 'pgn',
      data: opts.data,
      player: opts.player,
      options: {
        depth: opts.depth,
        include_llm: opts.include_llm ?? false,
        skill_level: opts.skill_level,
      },
    })
    return res.data as GameAnalysis
  } catch (err) {
    handleError(err)
  }
}

export interface AnalyzeProfileOptions {
  username: string
  platform: 'lichess' | 'chess.com'
  num_games?: number
  color?: 'white' | 'black' | null
  include_coaching?: boolean
}

export async function analyzeProfile(opts: AnalyzeProfileOptions): Promise<ProfileAnalysis> {
  try {
    const res = await apiClient().post('/api/v1/analyze/profile', {
      username: opts.username,
      platform: opts.platform,
      num_games: opts.num_games ?? 10,
      color: opts.color ?? null,
      options: { include_coaching: opts.include_coaching ?? false },
    })
    return res.data as ProfileAnalysis
  } catch (err) {
    handleError(err)
  }
}

// ── Config ────────────────────────────────────────────────────────────────────

export async function getConfig(): Promise<Config> {
  try {
    const res = await apiClient().get('/api/v1/config')
    return res.data as Config
  } catch (err) {
    handleError(err)
  }
}

export async function updateConfig(settings: Record<string, string | number>): Promise<void> {
  try {
    await apiClient().put('/api/v1/config', { settings })
  } catch (err) {
    handleError(err)
  }
}
