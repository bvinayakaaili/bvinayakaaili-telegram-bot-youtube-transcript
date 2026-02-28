export default function StatCard({ icon: Icon, label, value, sub, color = 'accent' }) {
  const colors = {
    accent: 'text-accent bg-accent/10 border-accent/20',
    gold: 'text-gold bg-gold/10 border-gold/20',
    green: 'text-green-400 bg-green-400/10 border-green-400/20',
    purple: 'text-purple-400 bg-purple-400/10 border-purple-400/20',
  }

  return (
    <div className="stat-card animate-fade-in">
      <div className={`w-9 h-9 rounded-xl flex items-center justify-center border ${colors[color]}`}>
        <Icon size={17} />
      </div>
      <div>
        <p className="text-2xl font-display font-bold text-text-bright">
          {value ?? <span className="shimmer inline-block w-16 h-7 rounded" />}
        </p>
        <p className="text-sm text-subtle">{label}</p>
      </div>
      {sub && <p className="text-xs text-muted mt-auto">{sub}</p>}
    </div>
  )
}