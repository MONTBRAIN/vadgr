import { NavLink } from 'react-router-dom';
import { useTheme } from '../../hooks/useTheme';
import { PixelSun, PixelMoon } from '../ui/PixelIcon';
import petLogo from '../../../../docs/pet.svg';

const navItems = [
  { to: '/', label: 'Dashboard' },
  { to: '/agents', label: 'Agents' },
  { to: '/runs', label: 'Runs' },
  { to: '/settings', label: 'Settings' },
];

export function TopNav() {
  const { theme, toggle } = useTheme();

  return (
    <nav className="flex items-center justify-between px-12 h-[60px] border-b border-border bg-bg-nav sticky top-0 z-50 transition-colors duration-300">
      <div className="flex items-center gap-8">
        <NavLink to="/" className="flex items-center gap-2.5 no-underline">
          <img src={petLogo} width={23} height={23} alt="logo" className="pixel-bounce" />
          <span className="font-heading font-bold text-lg text-text-primary tracking-tight">Vadgr</span>
        </NavLink>
        <div className="flex items-center gap-1 ml-3">
          {navItems.map(({ to, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `px-4 py-2 rounded-lg text-[13px] transition-all no-underline ${
                  isActive
                    ? 'bg-accent/[0.14] text-accent font-medium'
                    : 'text-text-muted hover:text-text-primary'
                }`
              }
            >
              {label}
            </NavLink>
          ))}
        </div>
      </div>
      <button
        onClick={toggle}
        className="w-9 h-9 rounded-[10px] border border-border bg-transparent cursor-pointer flex items-center justify-center transition-all hover:border-border-hover"
        title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
      >
        {theme === 'dark' ? (
          <PixelSun size={16} color="var(--color-warning)" />
        ) : (
          <PixelMoon size={16} color="var(--color-info)" />
        )}
      </button>
    </nav>
  );
}
