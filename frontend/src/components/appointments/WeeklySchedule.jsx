import { inputClass } from '../ui'
import { WEEKDAYS } from './options'

/** Weekly working hours: one row per day, any number of time blocks per day. */
export default function WeeklySchedule({ blocks, onChange, readOnly }) {
  const forDay = (d) => blocks.map((b, i) => ({ ...b, i })).filter((b) => b.weekday === d)
  const update = (i, key, value) => onChange(blocks.map((b, j) => (j === i ? { ...b, [key]: value } : b)))

  return (
    <div className="divide-y divide-slate-100">
      {WEEKDAYS.map((name, d) => (
        <div key={d} className="flex flex-wrap items-center gap-3 py-2.5">
          <span className="w-12 text-sm font-medium text-slate-700">{name}</span>
          {forDay(d).length === 0 && <span className="text-sm text-slate-400">Off</span>}
          {forDay(d).map((b) =>
            readOnly ? (
              <span key={b.i} className="rounded bg-slate-100 px-2 py-1 text-sm text-slate-700">
                {b.start}-{b.end}
              </span>
            ) : (
              <span key={b.i} className="flex items-center gap-1">
                <input
                  type="time"
                  className={`${inputClass} w-28 py-1`}
                  value={b.start}
                  onChange={(e) => update(b.i, 'start', e.target.value)}
                />
                -
                <input
                  type="time"
                  className={`${inputClass} w-28 py-1`}
                  value={b.end}
                  onChange={(e) => update(b.i, 'end', e.target.value)}
                />
                <button
                  type="button"
                  className="px-1 text-red-600"
                  title="Remove"
                  onClick={() => onChange(blocks.filter((_, j) => j !== b.i))}
                >
                  x
                </button>
              </span>
            ),
          )}
          {!readOnly && (
            <button
              type="button"
              className="text-sm text-brand-600 hover:underline"
              onClick={() => onChange([...blocks, { weekday: d, start: '09:00', end: '13:00' }])}
            >
              + Hours
            </button>
          )}
        </div>
      ))}
    </div>
  )
}
