import { useState, useEffect } from 'react'
import { Search, Film } from 'lucide-react'
import VideoCard from '../components/VideoCard'
import { getVideos } from '../utils/api'

export default function Videos() {
  const [data, setData] = useState(null)
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    getVideos(page)
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [page])

  const filtered = search
    ? data?.videos?.filter(v =>
        v.title?.toLowerCase().includes(search.toLowerCase()) ||
        v.channel?.toLowerCase().includes(search.toLowerCase())
      )
    : data?.videos

  return (
    <div className="page-enter space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold text-text-bright">Video Library</h1>
          <p className="text-subtle text-sm mt-1">{data?.total ?? 0} videos processed</p>
        </div>
      </div>

      {/* Search */}
      <div className="relative">
        <Search size={15} className="absolute left-4 top-1/2 -translate-y-1/2 text-muted" />
        <input
          className="input pl-10"
          placeholder="Search by title or channel…"
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
      </div>

      {/* List */}
      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3, 4].map(i => (
            <div key={i} className="card p-4 flex gap-4">
              <div className="shimmer w-32 h-20 rounded-xl" />
              <div className="flex-1 space-y-2 py-1">
                <div className="shimmer h-4 rounded w-3/4" />
                <div className="shimmer h-3 rounded w-1/4" />
                <div className="shimmer h-3 rounded w-2/3" />
              </div>
            </div>
          ))}
        </div>
      ) : filtered?.length ? (
        <div className="space-y-3">
          {filtered.map(v => <VideoCard key={v.video_id} video={v} />)}
        </div>
      ) : (
        <div className="card p-16 text-center">
          <Film size={32} className="text-muted mx-auto mb-3" />
          <p className="font-medium text-soft">No videos found</p>
          <p className="text-sm text-muted mt-1">
            {search ? 'Try a different search term' : 'Send a YouTube link to your Telegram bot'}
          </p>
        </div>
      )}

      {/* Pagination */}
      {data && data.pages > 1 && (
        <div className="flex items-center justify-center gap-2">
          <button
            className="btn-ghost text-sm"
            disabled={page <= 1}
            onClick={() => setPage(p => p - 1)}
          >
            ← Prev
          </button>
          <span className="text-sm text-subtle px-3">
            Page {page} of {data.pages}
          </span>
          <button
            className="btn-ghost text-sm"
            disabled={page >= data.pages}
            onClick={() => setPage(p => p + 1)}
          >
            Next →
          </button>
        </div>
      )}
    </div>
  )
}