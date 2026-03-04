import { useState, useEffect } from 'react'
import { getHealth, getConfig, updateConfig } from '../services/api'
import type { HealthStatus } from '../types/analysis'

// Local state for editing (flat structure for form)
interface FormState {
  stockfish_depth: number
  stockfish_path: string
  llm_model: string
  llm_base_url: string
}

export default function SettingsPage() {
  const [baseUrl, setBaseUrl] = useState(
    () => localStorage.getItem('api_base_url') || 'http://localhost:8000',
  )

  const [health, setHealth] = useState<HealthStatus | null>(null)
  const [healthError, setHealthError] = useState<string | null>(null)
  const [healthLoading, setHealthLoading] = useState(false)

  const [form, setForm] = useState<FormState>({
    stockfish_depth: 18,
    stockfish_path: '',
    llm_model: '',
    llm_base_url: '',
  })
  const [configLoading, setConfigLoading] = useState(false)
  const [configError, setConfigError] = useState<string | null>(null)
  const [configSaved, setConfigSaved] = useState(false)

  useEffect(() => {
    loadConfig()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function loadConfig() {
    setConfigLoading(true)
    setConfigError(null)
    try {
      const c = await getConfig()
      // Map nested structure to flat form
      setForm({
        stockfish_depth: c.stockfish?.depth ?? 18,
        stockfish_path: c.stockfish?.path ?? '',
        llm_model: c.llm?.model ?? '',
        llm_base_url: c.llm?.base_url ?? '',
      })
    } catch (err) {
      setConfigError(err instanceof Error ? err.message : 'Failed to load config')
    } finally {
      setConfigLoading(false)
    }
  }

  async function testConnection() {
    localStorage.setItem('api_base_url', baseUrl)
    setHealth(null)
    setHealthError(null)
    setHealthLoading(true)
    try {
      const h = await getHealth()
      setHealth(h)
    } catch (err) {
      setHealthError(err instanceof Error ? err.message : 'Connection failed')
    } finally {
      setHealthLoading(false)
    }
  }

  async function saveConfig(e: React.FormEvent) {
    e.preventDefault()
    setConfigLoading(true)
    setConfigError(null)
    setConfigSaved(false)
    try {
      // Convert flat form to dot-notation keys expected by backend
      const settings: Record<string, string | number> = {}
      if (form.stockfish_depth) settings['stockfish.depth'] = form.stockfish_depth
      if (form.stockfish_path) settings['stockfish.path'] = form.stockfish_path
      if (form.llm_model) settings['llm.model'] = form.llm_model
      if (form.llm_base_url) settings['llm.base_url'] = form.llm_base_url
      
      await updateConfig(settings)
      setConfigSaved(true)
      setTimeout(() => setConfigSaved(false), 3000)
    } catch (err) {
      setConfigError(err instanceof Error ? err.message : 'Failed to save config')
    } finally {
      setConfigLoading(false)
    }
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div>
        <h1 className="text-xl font-bold">Settings</h1>
        <p className="text-gray-500 text-sm mt-1">Configure server connection and analysis parameters</p>
      </div>

      {/* Server URL */}
      <div className="card space-y-4">
        <h2 className="font-semibold">Server Connection</h2>
        <div>
          <label className="label">API Server URL</label>
          <input
            className="input"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder="http://localhost:8000"
          />
          <p className="text-xs text-gray-600 mt-1">
            This is stored locally in your browser. Changing this will affect all API calls.
          </p>
        </div>
        <button onClick={testConnection} disabled={healthLoading} className="btn-secondary">
          {healthLoading ? 'Testing…' : 'Test Connection'}
        </button>

        {health && (
          <div className="text-sm space-y-1.5 p-3 bg-gray-800/50 rounded-lg">
            <div className="flex justify-between">
              <span className="text-gray-400">Status</span>
              <span className="text-green-400">✅ {health.status}</span>
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

      {/* Analysis Config */}
      <form onSubmit={saveConfig} className="card space-y-4">
        <h2 className="font-semibold">Analysis Configuration</h2>

        {configLoading && !form.stockfish_depth ? (
          <p className="text-sm text-gray-500">Loading config…</p>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="label">Default Stockfish Depth</label>
                <input
                  className="input"
                  type="number"
                  min={8}
                  max={30}
                  value={form.stockfish_depth}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, stockfish_depth: Number(e.target.value) }))
                  }
                />
              </div>
              <div>
                <label className="label">LLM Base URL</label>
                <input
                  className="input"
                  value={form.llm_base_url}
                  onChange={(e) => setForm((f) => ({ ...f, llm_base_url: e.target.value }))}
                  placeholder="http://localhost:1234/v1"
                />
              </div>
            </div>

            <div>
              <label className="label">LLM Model</label>
              <input
                className="input"
                value={form.llm_model}
                onChange={(e) => setForm((f) => ({ ...f, llm_model: e.target.value }))}
                placeholder="e.g. mistral-7b-instruct"
              />
            </div>

            <div>
              <label className="label">Stockfish Path</label>
              <input
                className="input"
                value={form.stockfish_path}
                onChange={(e) => setForm((f) => ({ ...f, stockfish_path: e.target.value }))}
                placeholder="/usr/local/bin/stockfish"
              />
            </div>

            {configError && (
              <div className="text-sm text-red-400 bg-red-500/10 border border-red-800 rounded-lg p-3">
                {configError}
              </div>
            )}
            {configSaved && (
              <div className="text-sm text-green-400 bg-green-500/10 border border-green-800 rounded-lg p-3">
                ✅ Configuration saved successfully
              </div>
            )}

            <button type="submit" disabled={configLoading} className="btn-primary">
              {configLoading ? 'Saving…' : 'Save Configuration'}
            </button>
          </>
        )}
      </form>
    </div>
  )
}
