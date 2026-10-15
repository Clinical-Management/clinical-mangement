import Logo from './Logo'

export default function AuthCard({ title, children }) {
  return (
    <div className="grid min-h-screen place-items-center bg-brand-gradient px-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex justify-center">
          <Logo light />
        </div>
        <div className="rounded-xl bg-white p-8 shadow-xl shadow-brand-900/20">
          <h1 className="mb-6 text-xl font-semibold text-slate-800">{title}</h1>
          {children}
        </div>
      </div>
    </div>
  )
}
