import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import RequireAuth from './components/layout/RequireAuth'
import Layout from './components/layout/Layout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Signals from './pages/Signals'
import Positions from './pages/Positions'
import Candidates from './pages/Candidates'
import AccumulationPositions from './pages/AccumulationPositions'
import StrategyLab from './pages/StrategyLab'
import Calibration from './pages/Calibration'
import Postmortem from './pages/Postmortem'
import Glossary from './pages/Glossary'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
    },
  },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route element={<RequireAuth />}>
            <Route element={<Layout />}>
              <Route index element={<Dashboard />} />
              <Route path="signals" element={<Signals />} />
              <Route path="positions" element={<Positions />} />
              <Route path="candidates" element={<Candidates />} />
              <Route path="accumulation" element={<AccumulationPositions />} />
              <Route path="strategy-lab" element={<StrategyLab />} />
              <Route path="calibration" element={<Calibration />} />
              <Route path="postmortem" element={<Postmortem />} />
              <Route path="glossary" element={<Glossary />} />
            </Route>
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
