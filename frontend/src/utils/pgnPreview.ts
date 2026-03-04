/**
 * Client-side PGN parser for instant board preview.
 *
 * Parses PGN headers and replays moves entirely in the browser using chess.js,
 * so the board and game metadata appear immediately after the user pastes a PGN
 * — no backend round-trip required.
 */

import { Chess } from 'chess.js'
import type { GameMetadata } from '../types/analysis'

export interface PgnPreview {
  /** Metadata extracted from PGN headers */
  metadata: GameMetadata
  /** FEN string for every position: index 0 = start, index N = after move N */
  fens: string[]
  /** Move list in SAN notation (e.g. ["e4", "e5", "Nf3", ...]) */
  moveSans: string[]
  /** Whether the PGN was parsed successfully */
  valid: boolean
  /** Parse error message if valid === false */
  error?: string
}

const EMPTY_META: GameMetadata = {
  white_player: '?',
  black_player: '?',
  white_elo: null,
  black_elo: null,
  event: '',
  site: '',
  date: null,
  result: '*',
  opening: '',
  eco: '',
}

/**
 * Parse a PGN string and return a PgnPreview with metadata, FEN array, and
 * SAN move list. Safe to call on every keystroke — all work is synchronous
 * and stays under ~5 ms for normal games.
 */
export function parsePgnPreview(pgn: string): PgnPreview {
  if (!pgn.trim()) {
    return { metadata: EMPTY_META, fens: [new Chess().fen()], moveSans: [], valid: false }
  }

  try {
    const loader = new Chess()
    loader.loadPgn(pgn)

    const headers = loader.header()
    const metadata: GameMetadata = {
      white_player: headers['White'] || '?',
      black_player: headers['Black'] || '?',
      white_elo: headers['WhiteElo'] ? parseInt(headers['WhiteElo'], 10) || null : null,
      black_elo: headers['BlackElo'] ? parseInt(headers['BlackElo'], 10) || null : null,
      event: headers['Event'] || '',
      site: headers['Site'] || '',
      date: headers['Date'] || null,
      result: headers['Result'] || '*',
      opening: headers['Opening'] || '',
      eco: headers['ECO'] || '',
    }

    // Build FEN array by replaying from start
    const history = loader.history({ verbose: true })
    const walker = new Chess()
    const fens: string[] = [walker.fen()]
    const moveSans: string[] = []

    for (const move of history) {
      walker.move(move.san)
      fens.push(walker.fen())
      moveSans.push(move.san)
    }

    return { metadata, fens, moveSans, valid: true }
  } catch (err) {
    return {
      metadata: EMPTY_META,
      fens: [new Chess().fen()],
      moveSans: [],
      valid: false,
      error: err instanceof Error ? err.message : 'Invalid PGN',
    }
  }
}
