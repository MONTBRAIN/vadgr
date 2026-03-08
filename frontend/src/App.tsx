import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Layout } from './components/layout/Layout';
import { Dashboard } from './pages/Dashboard';
import { AgentList } from './pages/AgentList';
import { AgentEditor } from './pages/AgentEditor';
import { AgentDetail } from './pages/AgentDetail';
import { RunList } from './pages/RunList';
import { RunViewer } from './pages/RunViewer';
import { Settings } from './pages/Settings';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 10_000,
      retry: 1,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<Dashboard />} />
            <Route path="/agents" element={<AgentList />} />
            <Route path="/agents/new" element={<AgentEditor />} />
            <Route path="/agents/:id" element={<AgentDetail />} />
            <Route path="/agents/:id/edit" element={<AgentEditor />} />
            <Route path="/runs" element={<RunList />} />
            <Route path="/runs/:id" element={<RunViewer />} />
            <Route path="/settings" element={<Settings />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
