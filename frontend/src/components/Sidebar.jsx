import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard, Film, Users, MessageSquare,
  Settings, Youtube, Zap, Globe
} from 'lucide-react'

const nav = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/videos', icon: Film, label: 'Videos' },
  { to: '/sessions', icon: Users, label: 'Sessions' },
  { to: '/playground', icon: Zap, label: 'Playground' },
]

export default function Sidebar() {
  return (
    <aside className="w-60 h-screen fixed left-0 top-0 bg-surface-1 border-r border-surface-3 flex flex-col z-40">
      {/* Logo */}
      <div className="px-6 py-6 border-b border-surface-3">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-accent to-blue-700 flex items-center justify-center">
            <Youtube size={18} className="text-white" />
          </div>
          <div>
            <p className="font-display font-bold text-text-bright text-base leading-none">YumiBot</p>
            <p className="text-xs text-muted mt-0.5">AI Dashboard</p>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 flex flex-col gap-1">
        {nav.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 ${
                isActive
                  ? 'bg-accent/15 text-accent border border-accent/20'
                  : 'text-subtle hover:text-text hover:bg-surface-3'
              }`
            }
          >
            <Icon size={16} />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="px-4 py-4 border-t border-surface-3">
        <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-surface-2">
          <Globe size={14} className="text-green-400" />
          <span className="text-xs text-soft">Bot Online</span>
          <span className="ml-auto w-2 h-2 rounded-full bg-green-400 animate-pulse-slow" />
        </div>
      </div>
    </aside>
  )
}