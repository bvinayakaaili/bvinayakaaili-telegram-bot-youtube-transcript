import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, Clock, ExternalLink, User, MessageSquare, Lightbulb, CheckCircle } from 'lucide-react'
import { getVideo, getVideoMessages } from '../utils/api'

function fmtDuration(secs) {
  if (!secs) return 'N/A'
  const h = Math.floor(secs / 3600)
  const m = Math.floor((secs % 3600) / 60)
  const s = secs % 60
  if (h) return `${h}h ${m}m`
  return `${m}m ${s}s`
}

export default function VideoDetail() {
  const { id } = useParams()
  const [video, setVideo] = useState(null)
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([getVideo(id), getVideoMessages(id)])
      .then(([v, m]) => { setVideo(v); setMessages(m) })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [id])

  if (loading) return (
    <div className="space-y-4 animate-pulse">
      <div className="shimmer h-6 w-48 rounded" />
      <div className="shimmer h-48 rounded-2xl" />
      <div className="shimmer h-64 rounded-2xl" />
    </div>
  )

  if (!video) return (
    <div className="card p-16 text-center">
      <p className="text-soft">Video not found</p>
      <Link to="/videos" className="btn-ghost mt-4 inline-flex">← Back</Link>
    </div>
  )

  return (
    <div className="page-enter space-y-6 max-w-4xl">
      {/* Back */}
      <Link to="/videos" className="inline-flex items-center gap-2 text-sm text-subtle hover:text-text transition-colors">
        <ArrowLeft size={15} /> Back to Videos
      </Link>

      {/* Hero */}
      <div className="card overflow-hidden">
        {video.thumbnail && (
          <img src={video.thumbnail} alt={video.title} className="w-full h-52 object-cover" />
        )}
        <div className="p-5">
          <h1 className="font-display font-bold text-text-bright text-xl leading-snug">{video.title}</h1>
          <div className="flex flex-wrap items-center gap-4 mt-3">
            <span className="text-sm text-subtle">{video.channel}</span>
            <span className="badge bg-surface-3 text-soft flex items-center gap-1">
              <Clock size={11} /> {fmtDuration(video.duration_secs)}
            </span>
            <a
              href={`https://youtube.com/watch?v=${video.video_id}`}
              target="_blank"
              rel="noreferrer"
              className="text-sm text-accent flex items-center gap-1 hover:underline"
            >
              <ExternalLink size={13} /> Watch on YouTube
            </a>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Summary */}
        <div className="lg:col-span-2 space-y-4">
          {/* Core insight */}
          {video.core_insight && (
            <div className="card p-5 border-l-2 border-accent">
              <div className="flex items-center gap-2 mb-2">
                <Lightbulb size={14} className="text-gold" />
                <p className="text-xs font-semibold text-gold uppercase tracking-wider">Core Insight</p>
              </div>
              <p className="text-text italic text-sm leading-relaxed">{video.core_insight}</p>
            </div>
          )}

          {/* Key Points */}
          {video.key_points?.length > 0 && (
            <div className="card p-5">
              <h2 className="font-display font-semibold text-text-bright mb-4 flex items-center gap-2">
                <CheckCircle size={16} className="text-accent" /> Key Points
              </h2>
              <ul className="space-y-3">
                {video.key_points.map((p, i) => (
                  <li key={i} className="flex items-start gap-3">
                    <span className="text-xs font-mono text-accent bg-accent/10 px-2 py-0.5 rounded mt-0.5 flex-shrink-0">
                      {String(i + 1).padStart(2, '0')}
                    </span>
                    <p className="text-sm text-text leading-relaxed">{p}</p>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Summary paragraph */}
          {video.summary && (
            <div className="card p-5">
              <h2 className="font-display font-semibold text-text-bright mb-3">Overview</h2>
              <p className="text-sm text-soft leading-relaxed">{video.summary}</p>
            </div>
          )}
        </div>

        {/* Timestamps + Messages */}
        <div className="space-y-4">
          {/* Timestamps */}
          {video.timestamps?.length > 0 && (
            <div className="card p-4">
              <h2 className="font-display font-semibold text-text-bright mb-3 text-sm">Timestamps</h2>
              <div className="space-y-2">
                {video.timestamps.map((t, i) => (
                  <div key={i} className="flex items-start gap-2">
                    <span className="font-mono text-xs text-accent bg-accent/10 px-1.5 py-0.5 rounded flex-shrink-0">
                      {t.time}
                    </span>
                    <p className="text-xs text-soft leading-snug">{t.label}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Q&A Messages */}
          {messages.length > 0 && (
            <div className="card p-4">
              <h2 className="font-display font-semibold text-text-bright mb-3 text-sm flex items-center gap-2">
                <MessageSquare size={14} className="text-accent" />
                Conversations ({messages.length})
              </h2>
              <div className="space-y-3 max-h-80 overflow-y-auto pr-1">
                {messages.map((m, i) => (
                  <div
                    key={i}
                    className={`text-xs px-3 py-2 rounded-xl leading-relaxed ${
                      m.role === 'user'
                        ? 'bg-accent/10 text-accent border border-accent/20 ml-4'
                        : 'bg-surface-3 text-soft mr-4'
                    }`}
                  >
                    <p className="font-semibold mb-1 text-[10px] uppercase tracking-wider opacity-70">
                      {m.role === 'user' ? '👤 User' : '🤖 Bot'}
                    </p>
                    {m.content}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}