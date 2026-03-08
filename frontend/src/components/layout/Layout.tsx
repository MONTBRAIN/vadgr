import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';

export function Layout() {
  return (
    <div className="min-h-screen bg-bg-primary">
      <Sidebar />
      <main className="ml-56 p-8">
        <Outlet />
      </main>
    </div>
  );
}
