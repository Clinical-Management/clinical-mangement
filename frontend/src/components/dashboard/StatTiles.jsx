import { Link } from 'react-router-dom'
import { cardClass } from '../ui'

/** Headline numbers for today. Each tile links to where the work happens. */
export default function StatTiles({ tiles }) {
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {tiles.map((t) => (
        <Link key={t.label} to={t.to} className={`${cardClass} p-4! transition hover:border-accent-600`}>
          <p className="text-3xl font-semibold text-slate-800">{t.value}</p>
          <p className="text-sm text-slate-500">{t.label}</p>
        </Link>
      ))}
    </div>
  )
}
