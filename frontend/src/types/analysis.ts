// TypeScript types mirroring the Chess Coach API schemas

export interface PlayerStats {
  accuracy: number
  brilliant: number
  great: number
  best: number
  excellent: number
  good: number
  inaccuracy: number
  mistake: number
  blunder: number
  forced: number
  total_moves: number
  average_eval_loss: number
}

export type MoveClassification =
  | 'brilliant'
  | 'great'
  | 'best'
  | 'excellent'
  | 'good'
  | 'inaccuracy'
  | 'mistake'
  | 'blunder'
  | 'forced'

export interface MoveAnalysis {
  move_number: number
  move_san: string
  move_uci: string
  player_color: 'white' | 'black'
  classification: MoveClassification
  eval_loss: number
  move_accuracy: number
  is_blunder: boolean
  is_mistake: boolean
  is_inaccuracy: boolean
  mistake_type: string | null
  comment: string
}

export interface GameMetadata {
  white_player: string
  black_player: string
  white_elo: number | null
  black_elo: number | null
  event: string
  site: string
  date: string | null
  result: string
  opening: string
  eco: string
}

export interface GameAnalysis {
  game_id: string
  metadata: GameMetadata
  moves: MoveAnalysis[]
  white_stats: PlayerStats
  black_stats: PlayerStats
  total_moves: number
  blunders: number
  mistakes: number
  inaccuracies: number
  average_eval_loss: number
  ai_summary: string
  ai_strengths: string[]
  ai_weaknesses: string[]
  ai_recommendations: string[]
  analysis_time: number
}

export interface Pattern {
  pattern_type: string
  description: string
  occurrences: number
  severity: 'low' | 'medium' | 'high'
  examples: number[]
}

export interface ProfileAnalysis {
  username: string
  platform: string
  num_games_analyzed: number
  average_accuracy: number
  aggregated_stats: PlayerStats
  patterns: Pattern[]
  opening_analysis: Record<string, { games: number; avg_errors: number }>
  phase_analysis: Record<string, { moves: number; error_rate: number; avg_loss: number }>
}

export interface HealthStatus {
  status: string
  stockfish: string
  llm_configured: boolean
  llm_model: string
  llm_provider: string
  active_analyses: number
  cache_entries: number
  uptime_seconds: number
}

// Config matches backend GET /api/v1/config response
export interface Config {
  llm: { provider: string; model: string; base_url: string | null }
  stockfish: { path: string; depth: number; time_limit: number }
  data: { data_dir: string; cache_dir: string; logs_dir: string }
  api: { username: string }
}

export type WsPingMessage = { type: 'ping' }

export type WsProgressMessage = {
  type: 'progress'
  percent: number
  current: number
  total: number
}

export type WsResultMessage = {
  type: 'result'
  analysis: GameAnalysis | ProfileAnalysis
}

export type WsErrorMessage = {
  type: 'error'
  message: string
}

export type WsMessage = WsPingMessage | WsProgressMessage | WsResultMessage | WsErrorMessage
