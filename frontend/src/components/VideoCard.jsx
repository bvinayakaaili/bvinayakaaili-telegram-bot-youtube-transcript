import { Link } from 'react-router-dom'
import { Clock, MessageSquare, ExternalLink } from 'lucide-react'

function fmtDuration(secs) {
  if (!secs) return ''
  const m = Math.floor(secs / 60)
  const s = secs % 60
  const h = Math.floor(m / 60)
  if (h) return `${h}h ${m % 60}m`
  return `${m}:${String(s).padStart(2, '0')}`
}

export default function VideoCard({ video }) {
  return (
    <Link
      to={`/videos/${video.video_id}`}
      className="card p-4 flex gap-4 hover:border-accent/30 transition-all duration-300 group animate-slide-up"
    >
      {/* Thumbnail */}
      <div className="relative flex-shrink-0 w-32 h-20 rounded-xl overflow-hidden bg-surface-3">
        {video.thumbnail ? (
          <img src={video.thumbnail} alt={video.title} className="w-full h-full object-cover" />
        ) : (
          <div className="w-full h-full bg-gradient-to-br from-surface-3 to-surface-4 flex items-center justify-center">
            <span className="text-2xl">🎬</span>
          </div>
        )}
        {video.duration_secs > 0 && (
          <span className="absolute bottom-1 right-1 text-xs bg-black/80 text-white px-1.5 py-0.5 rounded font-mono">
            {fmtDuration(video.duration_secs)}
          </span>
        )}
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0 flex flex-col gap-1">
        <p className="font-semibold text-text-bright text-sm line-clamp-2 group-hover:text-accent transition-colors">
          {video.title || 'Unknown Title'}
        </p>
        <p className="text-xs text-muted">{video.channel}</p>
        {video.core_insight && (
          <p className="text-xs text-subtle line-clamp-2 mt-1 italic">
            {video.core_insight}
          </p>
        )}
        <div className="flex items-center gap-3 mt-auto">
          <span className="text-xs text-muted flex items-center gap-1">
            <Clock size={11} />
            {video.created_at ? new Date(video.created_at).toLocaleDateString() : ''}
          </span>
          <a
            href={`https://youtube.com/watch?v=${video.video_id}`}
            target="_blank"
            rel="noreferrer"
            onClick={e => e.stopPropagation()}
            className="text-xs text-accent flex items-center gap-1 hover:underline"
          >
            <ExternalLink size={11} /> Watch
          </a>
        </div>
      </div>
    </Link>
  )
}