import { NavLink, Outlet } from 'react-router-dom'
import { useAuthStore } from '../store/authStore'
import clsx from 'clsx'

const NAV_LINKS = [
  { to: '/', label: '♟ Chess Coach', exact: true },
  { to: '/game', label: 'Game Analysis' },
  { to: '/profile', label: 'Profile Analysis' },
  { to: '/settings', label: 'Settings' },
]

export default function Layout() {
  const { username, clearAuth } = useAuthStore()

  return (
    <div className="min-h-screen flex flex-col">
      {/* Top nav */}
      <header className="bg-gray-900 border-b border-gray-800 px-6 py-3 flex items-center justify-between sticky top-0 z-50">
        <nav className="flex items-center gap-6">
          {NAV_LINKS.map(({ to, label, exact }) => (
            <NavLink
              key={to}
              to={to}
              end={exact}
              className={({ isActive }) =>
                clsx(
                  'text-sm font-medium transition-colors',
                  to === '/'
                    ? 'text-brand-400 font-bold text-base'
                    : isActive
                    ? 'text-white'
                    : 'text-gray-400 hover:text-gray-200',
                )
              }
            >
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="flex items-center gap-3 text-sm text-gray-400">
          {username && (
            <>
              <span className="text-gray-500">
                Logged in as <span className="text-gray-200">{username}</span>
              </span>
              <button
                onClick={clearAuth}
                className="text-brand-400 hover:text-brand-300 transition-colors"
              >
                Logout
              </button>
            </>
          )}
        </div>
      </header>

      {/* Page content */}
      <main className="flex-1 container mx-auto max-w-7xl px-6 py-8">
        <Outlet />
      </main>

      <footer className="text-center text-xs text-gray-700 py-4 border-t border-gray-900">
        Chess Coach · Powered by Stockfish + AI · Running locally
      </footer>
    </div>
  )
}
