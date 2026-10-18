const STYLE = {
  high: { box: 'border-red-300 bg-red-50 text-red-800', icon: '!!', label: 'Serious' },
  moderate: { box: 'border-amber-300 bg-amber-50 text-amber-900', icon: '!', label: 'Caution' },
  info: { box: 'border-slate-200 bg-slate-50 text-slate-700', icon: 'i', label: 'Note' },
}
const TYPE = { allergy: 'Allergy', interaction: 'Interaction', duplicate: 'Duplicate therapy', dose: 'Dose' }

/** Allergy, interaction, duplicate-therapy and dose-range warnings, most serious first. */
export default function ChecksPanel({ checks }) {
  if (!checks.length) {
    return <p className="rounded-md bg-accent-50 px-3 py-2 text-sm text-accent-700">✓ No allergy, interaction, duplicate or dose warnings</p>
  }
  const order = { high: 0, moderate: 1, info: 2 }
  return (
    <ul className="space-y-1.5">
      {[...checks]
        .sort((a, b) => order[a.severity] - order[b.severity])
        .map((c, i) => {
          const s = STYLE[c.severity]
          return (
            <li key={i} className={`rounded-md border px-3 py-2 text-sm ${s.box}`}>
              <b>
                {s.icon} {s.label} - {TYPE[c.type]}:
              </b>{' '}
              {c.medicines.join(' + ')}: {c.message}
            </li>
          )
        })}
    </ul>
  )
}
