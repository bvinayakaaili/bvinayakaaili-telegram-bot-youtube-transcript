import { useState } from 'react'
import { Zap, Youtube, Globe, CheckCircle, Clock, Lightbulb, ChevronRight } from 'lucide-react'
import { processVideo } from '../utils/api'

const LANGUAGES = [
  { code: 'en', label: '🇬🇧 English' },
  { code: 'hi', label: '🇮🇳 Hindi' },
  { code: 'ta', label: 'Tamil' },
  { code: 'te', label: 'Telugu' },
  { code: 'kn', label: 'Kannada' },
  { code: 'mr', label: 'Marathi' },
]

const EXAMPLES = [
  'https://youtube.com/watch?v=dQw4w9WgXcQ',
  'https://youtu.be/XXXXX',
]

export default function Playground() {
  const [url, setUrl] = useState('')
  const [lang, setLang] = useState('en')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [phase, setPhase] = useState('')

  const phases = [
    'Extracting video ID…',
    'Fetching transcript…',
    'Loading metadata…',
    'Generating AI summary…',
  ]

  async function handleSubmit() {
    if (!url.trim()) return
    setLoading(true)
    setError(null)
    setResult(null)

    // Simulate phase messages
    let phaseIdx = 0
    const phaseTimer = setInterval(() => {
      setPhase(phases[Math.min(phaseIdx, phases.length - 1)])
      phaseIdx++
    }, 2000)

    try {
      const data = await processVideo(url.trim(), lang)
      setResult(data)
    } catch (e) {
      setError(e.response?.data?.error || e.message || 'An error occurred')
    } finally {
      clearInterval(phaseTimer)
      setLoading(false)
      setPhase('')
    }
  }

  return (
    <div className="page-enter space-y-6 max-w-3xl">
      <div>
        <h1 className="font-display text-2xl font-bold text-text-bright flex items-center gap-2">
          <Zap size={22} className="text-gold" /> Playground
        </h1>
        <p className="text-subtle text-sm mt-1">Test the summarizer directly from the web interface</p>
      </div>

      {/* Input card */}
      <div className="card p-6 space-y-5">
        <div>
          <label className="text-xs font-semibold text-muted uppercase tracking-wider mb-2 block">
            YouTube URL
          </label>
          <div className="relative">
            <Youtube size={15} className="absolute left-4 top-1/2 -translate-y-1/2 text-muted" />
            <input
              className="input pl-10"
              placeholder="https://youtube.com/watch?v=..."
              value={url}
              onChange={e => setUrl(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSubmit()}
            />
          </div>
        </div>

        <div>
          <label className="text-xs font-semibold text-muted uppercase tracking-wider mb-2 block flex items-center gap-1.5">
            <Globe size={12} /> Output Language
          </label>
          <div className="flex flex-wrap gap-2">
            {LANGUAGES.map(l => (
              <button
                key={l.code}
                onClick={() => setLang(l.code)}
                className={`text-sm px-3 py-1.5 rounded-lg border transition-all duration-200 ${
                  lang === l.code
                    ? 'bg-accent/15 text-accent border-accent/40'
                    : 'bg-surface-3 text-subtle border-surface-4 hover:border-surface-3 hover:text-text'
                }`}
              >
                {l.label}
              </button>
            ))}
          </div>
        </div>

        <button
          onClick={handleSubmit}
          disabled={loading || !url.trim()}
          className="btn-primary w-full justify-center disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading ? (
            <>
              <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              {phase || 'Processing…'}
            </>
          ) : (
            <>
              <Zap size={16} /> Generate Summary
            </>
          )}
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="card p-4 border-red-500/30 bg-red-500/5">
          <p className="text-red-400 text-sm">⚠️ {error}</p>
        </div>
      )}

      {/* Result */}
      {result && (
        <div className="space-y-4 animate-slide-up">
          {result.cached && (
            <div className="flex items-center gap-2 text-xs text-gold bg-gold/10 border border-gold/20 rounded-xl px-4 py-2">
              ⚡ Loaded from cache
            </div>
          )}

          {/* Video info */}
          <div className="card overflow-hidden">
            {result.thumbnail && (
              <img src={result.thumbnail} alt={result.title} className="w-full h-44 object-cover" />
            )}
            <div className="p-5">
              <h2 className="font-display font-bold text-text-bright text-lg">{result.title}</h2>
              <p className="text-sm text-muted mt-1">{result.channel}</p>
            </div>
          </div>

          {/* Core insight */}
          {result.core_insight && (
            <div className="card p-5 border-l-2 border-gold">
              <div className="flex items-center gap-2 mb-2">
                <Lightbulb size={13} className="text-gold" />
                <span className="text-xs font-bold text-gold uppercase tracking-wider">Core Insight</span>
              </div>
              <p className="text-sm text-text italic">{result.core_insight}</p>
            </div>
          )}

          {/* Key points */}
          {result.key_points?.length > 0 && (
            <div className="card p-5">
              <h3 className="font-display font-semibold text-text-bright mb-4 flex items-center gap-2">
                <CheckCircle size={15} className="text-accent" /> Key Points
              </h3>
              <ul className="space-y-3">
                {result.key_points.map((p, i) => (
                  <li key={i} className="flex items-start gap-3">
                    <span className="text-xs font-mono text-accent bg-accent/10 px-1.5 py-0.5 rounded mt-0.5 flex-shrink-0">
                      {String(i + 1).padStart(2, '0')}
                    </span>
                    <p className="text-sm text-text leading-relaxed">{p}</p>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Timestamps */}
          {result.timestamps?.length > 0 && (
            <div className="card p-5">
              <h3 className="font-display font-semibold text-text-bright mb-4 flex items-center gap-2">
                <Clock size={15} className="text-accent" /> Timestamps
              </h3>
              <div className="space-y-2">
                {result.timestamps.map((t, i) => (
                  <div key={i} className="flex items-center gap-3">
                    <span className="font-mono text-xs bg-accent/10 text-accent px-2 py-0.5 rounded w-16 text-center flex-shrink-0">
                      {t.time}
                    </span>
                    <ChevronRight size={12} className="text-muted flex-shrink-0" />
                    <p className="text-sm text-soft">{t.label}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Action Points */}
          {result.action_points?.length > 0 && (
            <div className="card p-5">
              <h3 className="font-display font-semibold text-text-bright mb-4">✅ Action Points</h3>
              <ul className="space-y-2">
                {result.action_points.map((a, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-soft">
                    <span className="text-green-400 mt-0.5 flex-shrink-0">•</span>
                    {a}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Summary */}
          {result.summary && (
            <div className="card p-5">
              <h3 className="font-display font-semibold text-text-bright mb-3">Overview</h3>
              <p className="text-sm text-soft leading-relaxed">{result.summary}</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}