import { useEffect, useMemo, useRef, useState } from 'react'
import { FLAG_META } from '../clinical/vitalsMeta'

const HEIGHT = 170
const PAD = { top: 14, right: 44, bottom: 24, left: 36 }

function niceTicks(min, max, count = 4) {
  const span = max - min || 1
  const step = 10 ** Math.floor(Math.log10(span / count))
  const err = span / count / step
  const nice = step * (err >= 7.5 ? 10 : err >= 3.5 ? 5 : err >= 1.5 ? 2 : 1)
  const ticks = []
  for (let v = Math.ceil(min / nice) * nice; v <= max + 1e-9; v += nice) ticks.push(Number(v.toFixed(6)))
  return ticks
}

const shortDate = (d) => d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' })

/**
 * Time-series line chart (one y-axis). series: [{ label, color, points: [{ t: Date, v, flag }] }].
 * `band` shades the normal range. Hover shows a crosshair + tooltip for the nearest reading.
 */
export default function LineChart({ series, band, unit, ariaLabel }) {
  const wrapper = useRef(null)
  const [width, setWidth] = useState(480)
  const [hover, setHover] = useState(null) // index into `times`

  useEffect(() => {
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(240, entry.contentRect.width)))
    observer.observe(wrapper.current)
    return () => observer.disconnect()
  }, [])

  const { times, x, y, yTicks } = useMemo(() => {
    const all = series.flatMap((s) => s.points)
    const times = [...new Set(all.map((p) => p.t.getTime()))].sort((a, b) => a - b)
    const values = all.map((p) => p.v).concat([band?.low, band?.high].filter((v) => v != null))
    let [lo, hi] = [Math.min(...values), Math.max(...values)]
    const pad = (hi - lo || Math.abs(hi) || 1) * 0.15
    ;[lo, hi] = [lo - pad, hi + pad]
    const ticks = niceTicks(lo, hi)
    lo = Math.min(lo, ticks[0])
    hi = Math.max(hi, ticks.at(-1))
    const [t0, t1] = times.length > 1 ? [times[0], times.at(-1)] : [times[0] - 864e5, times[0] + 864e5]
    const innerW = width - PAD.left - PAD.right
    const innerH = HEIGHT - PAD.top - PAD.bottom
    return {
      times,
      x: (t) => PAD.left + ((t - t0) / (t1 - t0)) * innerW,
      y: (v) => PAD.top + (1 - (v - lo) / (hi - lo)) * innerH,
      yTicks: ticks,
    }
  }, [series, band, width])

  const onMove = (e) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const px = e.clientX - rect.left
    let best = 0
    times.forEach((t, i) => {
      if (Math.abs(x(t) - px) < Math.abs(x(times[best]) - px)) best = i
    })
    setHover(best)
  }

  const hoverTime = hover != null ? times[hover] : null
  const hoverRows =
    hoverTime != null
      ? series
          .map((s) => ({ s, p: s.points.find((p) => p.t.getTime() === hoverTime) }))
          .filter((r) => r.p)
      : []

  return (
    <div ref={wrapper} className="relative">
      <svg
        width={width}
        height={HEIGHT}
        role="img"
        aria-label={ariaLabel}
        onPointerMove={onMove}
        onPointerLeave={() => setHover(null)}
        className="block touch-none"
      >
        {band && (band.low != null || band.high != null) && (
          <rect
            x={PAD.left}
            width={width - PAD.left - PAD.right}
            y={y(band.high ?? yTicks.at(-1))}
            height={Math.max(0, y(band.low ?? yTicks[0]) - y(band.high ?? yTicks.at(-1)))}
            fill="#e8f7f5"
          />
        )}
        {yTicks.map((t) => (
          <g key={t}>
            <line x1={PAD.left} x2={width - PAD.right} y1={y(t)} y2={y(t)} stroke="#e2e8f0" strokeWidth="1" />
            <text x={PAD.left - 6} y={y(t)} dy="0.32em" textAnchor="end" className="fill-slate-500 text-[10px]">
              {t}
            </text>
          </g>
        ))}
        {times.length > 0 && (
          <>
            <text x={x(times[0])} y={HEIGHT - 6} textAnchor="start" className="fill-slate-500 text-[10px]">
              {shortDate(new Date(times[0]))}
            </text>
            {times.length > 1 && (
              <text x={x(times.at(-1))} y={HEIGHT - 6} textAnchor="end" className="fill-slate-500 text-[10px]">
                {shortDate(new Date(times.at(-1)))}
              </text>
            )}
          </>
        )}

        {hoverTime != null && (
          <line x1={x(hoverTime)} x2={x(hoverTime)} y1={PAD.top} y2={HEIGHT - PAD.bottom} stroke="#94a3b8" strokeWidth="1" />
        )}

        {series.map((s) => (
          <g key={s.label}>
            <polyline
              fill="none"
              stroke={s.color}
              strokeWidth="2"
              strokeLinejoin="round"
              strokeLinecap="round"
              points={s.points.map((p) => `${x(p.t.getTime())},${y(p.v)}`).join(' ')}
            />
            {s.points.map((p) => (
              <circle
                key={p.t.getTime()}
                cx={x(p.t.getTime())}
                cy={y(p.v)}
                r={p.flag ? 5 : 4}
                fill={s.color}
                stroke={p.flag ? FLAG_META[p.flag].ring : '#ffffff'}
                strokeWidth="2"
              />
            ))}
            {/* direct label at the line end: latest value */}
            {s.points.length > 0 && (
              <text
                x={x(s.points.at(-1).t.getTime()) + 8}
                y={y(s.points.at(-1).v)}
                dy="0.32em"
                className="fill-slate-700 text-[11px] font-medium"
              >
                {s.points.at(-1).v}
              </text>
            )}
          </g>
        ))}
      </svg>

      {hoverRows.length > 0 && (
        <div
          className="pointer-events-none absolute top-1 z-10 rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs shadow-md"
          style={{ left: Math.min(x(hoverTime) + 10, width - 150) }}
        >
          <p className="mb-0.5 text-slate-500">{new Date(hoverTime).toLocaleDateString()}</p>
          {hoverRows.map(({ s, p }) => (
            <p key={s.label} className="flex items-center gap-1.5 text-slate-800">
              <span className="inline-block h-2 w-2 rounded-full" style={{ background: s.color }} />
              {s.label}: <b>{p.v}</b> {unit}
              {p.flag && (
                <span className={FLAG_META[p.flag].text}>
                  {FLAG_META[p.flag].icon} {FLAG_META[p.flag].label}
                </span>
              )}
            </p>
          ))}
        </div>
      )}
    </div>
  )
}
