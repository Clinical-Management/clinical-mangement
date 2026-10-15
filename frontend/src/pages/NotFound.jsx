import { Link } from 'react-router-dom'

export default function NotFound() {
  return (
    <div className="grid h-screen place-items-center text-center">
      <div>
        <h1 className="text-4xl font-bold text-slate-800">404</h1>
        <p className="mt-2 text-slate-500">Page not found.</p>
        <Link to="/" className="mt-4 inline-block text-brand-600 hover:underline">
          Go home
        </Link>
      </div>
    </div>
  )
}
