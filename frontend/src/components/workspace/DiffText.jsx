/** Word-level diff: additions highlighted, removals struck through. */
export default function DiffText({ ops }) {
  return (
    <p className="whitespace-pre-line text-sm leading-relaxed">
      {ops.map((o, i) =>
        o.op === 'insert' ? (
          <ins key={i} className="rounded bg-accent-100 px-0.5 text-accent-700 no-underline">
            {o.text}
          </ins>
        ) : o.op === 'delete' ? (
          <del key={i} className="rounded bg-red-50 px-0.5 text-red-700">
            {o.text}
          </del>
        ) : (
          <span key={i} className="text-slate-700">
            {o.text}
          </span>
        ),
      )}
    </p>
  )
}
