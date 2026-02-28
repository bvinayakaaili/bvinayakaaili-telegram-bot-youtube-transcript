import { useState, useEffect } from 'react'
import { Users, MessageSquare, Globe, Clock } from 'lucide-react'
import { getSessions } from '../utils/api'

export default function Sessions() {
  const [sessions, setSessions] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getSessions()
      .then(setSessions)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="page-enter space-y-6">
      <div>
        <h1 className="font-display text-2xl font-bold text-text-bright">User Sessions</h1>
        <p className="text-subtle text-sm mt-1">{sessions.length} Telegram users tracked</p>
      </div>

      {loading ? (
        <div className="space-y-3">
          {[1,2,3].map(i => <div key={i} className="card p-4 shimmer h-16" />)}
        </div>
      ) : sessions.length ? (
        <div className="card overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-surface-3">
                {['User', 'Language', 'Current Video', 'Messages', 'Last Active'].map(h => (
                  <th key={h} className="text-left text-xs text-muted font-medium px-5 py-3">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sessions.map((s, i) => (
                <tr key={i} className="border-b border-surface-3/50 hover:bg-surface-3/30 transition-colors">
                  <td className="px-5 py-3">
                    <div className="flex items-center gap-2">
                      <div className="w-7 h-7 rounded-full bg-accent/20 flex items-center justify-center">
                        <Users size={12} className="text-accent" />
                      </div>
                      <div>
                        <p className="text-text-bright font-medium">@{s.username || s.telegram_id}</p>
                        <p className="text-xs text-muted font-mono">{s.telegram_id}</p>
                      </div>
                    </div>
                  </td>
                  <td className="px-5 py-3">
                    <span className="badge bg-surface-3 text-soft flex items-center gap-1 w-fit">
                      <Globe size={10} /> {s.language}
                    </span>
                  </td>
                  <td className="px-5 py-3">
                    {s.current_video ? (
                      <a
                        href={`/videos/${s.current_video}`}
                        className="font-mono text-xs text-accent hover:underline"
                      >
                        {s.current_video}
                      </a>
                    ) : (
                      <span className="text-muted text-xs">—</span>
                    )}
                  </td>
                  <td className="px-5 py-3">
                    <span className="flex items-center gap-1 text-soft">
                      <MessageSquare size={12} /> {s.message_count}
                    </span>
                  </td>
                  <td className="px-5 py-3 text-xs text-muted">
                    {s.updated_at ? new Date(s.updated_at).toLocaleString() : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="card p-16 text-center">
          <Users size={32} className="text-muted mx-auto mb-3" />
          <p className="font-medium text-soft">No sessions yet</p>
          <p className="text-sm text-muted mt-1">Users will appear once they message your Telegram bot</p>
        </div>
      )}
    </div>
  )
}