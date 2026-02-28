import { useState, useEffect } from 'react'
import { Film, Users, MessageSquare, TrendingUp } from 'lucide-react'
import StatCard from '../components/StatCard'
import VideoCard from '../components/VideoCard'
import { getStats } from '../utils/api'

export default function Dashboard() {
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getStats()
      .then(setStats)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="page-enter space-y-8">
      {/* Header */}
      <div>
        <h1 className="font-display text-2xl font-bold text-text-bright">Overview</h1>
        <p className="text-subtle text-sm mt-1">Monitor your YouTube AI assistant's activity</p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          icon={Film}
          label="Videos Processed"
          value={stats?.total_videos ?? null}
          color="accent"
        />
        <StatCard
          icon={Users}
          label="Active Users"
          value={stats?.total_sessions ?? null}
          color="gold"
        />
        <StatCard
          icon={MessageSquare}
          label="Total Messages"
          value={stats?.total_messages ?? null}
          color="green"
        />
        <StatCard
          icon={TrendingUp}
          label="Messages Today"
          value={stats?.messages_today ?? null}
          color="purple"
        />
      </div>

      {/* Recent Videos */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-display font-semibold text-text-bright">Recent Videos</h2>
          <a href="/videos" className="text-sm text-accent hover:underline">View all →</a>
        </div>
        {loading ? (
          <div className="space-y-3">
            {[1, 2, 3].map(i => (
              <div key={i} className="card p-4 flex gap-4">
                <div className="shimmer w-32 h-20 rounded-xl" />
                <div className="flex-1 space-y-2">
                  <div className="shimmer h-4 rounded w-3/4" />
                  <div className="shimmer h-3 rounded w-1/3" />
                  <div className="shimmer h-3 rounded w-2/3" />
                </div>
              </div>
            ))}
          </div>
        ) : stats?.recent_videos?.length ? (
          <div className="space-y-3">
            {stats.recent_videos.map(v => (
              <VideoCard key={v.video_id} video={v} />
            ))}
          </div>
        ) : (
          <div className="card p-10 text-center">
            <p className="text-4xl mb-3">🎬</p>
            <p className="font-medium text-soft">No videos yet</p>
            <p className="text-sm text-muted mt-1">
              Send a YouTube link to your Telegram bot or use the Playground
            </p>
          </div>
        )}
      </div>

      {/* Setup Guide */}
      <div className="card p-6">
        <h2 className="font-display font-semibold text-text-bright mb-4">Quick Start Guide</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {[
            {
              step: '01',
              title: 'Setup Bot',
              desc: 'Create a bot on Telegram via @BotFather and add your token to .env',
              color: 'text-accent',
            },
            {
              step: '02',
              title: 'Send a Link',
              desc: 'Message your bot a YouTube URL to get an instant AI-powered summary',
              color: 'text-gold',
            },
            {
              step: '03',
              title: 'Ask Questions',
              desc: 'Follow up with any question about the video — grounded in transcript',
              color: 'text-green-400',
            },
          ].map(({ step, title, desc, color }) => (
            <div key={step} className="bg-surface-3 rounded-xl p-4">
              <p className={`font-mono text-xs font-bold ${color} mb-2`}>{step}</p>
              <p className="font-semibold text-text-bright text-sm mb-1">{title}</p>
              <p className="text-xs text-subtle">{desc}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}