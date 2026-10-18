/** Tiny trend line for one analyte across approved reports (current value ringed). */
export default function Sparkline({ points }) {
  if (!points || points.length < 2) return null
  const w = 84, h = 24, pad = 4
  const values = points.map((p) => p.value)
  const [lo, hi] = [Math.min(...values), Math.max(...values)]
  const x = (i) => pad + (i / (points.length - 1)) * (w - 2 * pad)
  const y = (v) => h - pad - ((v - lo) / (hi - lo || 1)) * (h - 2 * pad)
  const title = points.map((p) => `${p.date}: ${p.value}${p.unit ? ` ${p.unit}` : ''}${p.current ? ' (this report)' : ''}`).join('\n')
  return (
    <svg width={w} height={h} className="shrink-0" role="img" aria-label={`Trend: ${title}`}>
      <title>{title}</title>
      <polyline fill="none" stroke="#1a5ea6" strokeWidth="2" strokeLinejoin="round" points={points.map((p, i) => `${x(i)},${y(p.value)}`).join(' ')} />
      {points.map((p, i) => (
        <circle key={i} cx={x(i)} cy={y(p.value)} r={p.current ? 3.5 : 2.5} fill={p.current ? '#ffffff' : '#1a5ea6'} stroke="#1a5ea6" strokeWidth="1.5" />
      ))}
    </svg>
  )
}
