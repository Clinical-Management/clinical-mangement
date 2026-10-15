/** App mark + name. `light` for use on the brand gradient; `compact` hides the name on small screens. */
export default function Logo({ light = false, compact = false }) {
  return (
    <span className="flex items-center gap-2.5">
      <svg viewBox="0 0 32 32" className="h-8 w-8 shrink-0" aria-hidden="true">
        <defs>
          <linearGradient id="logo-gradient" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#023b77" />
            <stop offset="1" stopColor="#039583" />
          </linearGradient>
        </defs>
        <rect width="32" height="32" rx="8" fill={light ? '#ffffff' : 'url(#logo-gradient)'} />
        <path d="M13 8h6v5h5v6h-5v5h-6v-5H8v-6h5z" fill={light ? 'url(#logo-gradient)' : '#ffffff'} />
      </svg>
      <span
        className={`text-lg font-semibold tracking-tight ${light ? 'text-white' : 'text-brand-gradient'} ${
          compact ? 'hidden sm:inline' : ''
        }`}
      >
        Clinical Mgmt
      </span>
    </span>
  )
}
