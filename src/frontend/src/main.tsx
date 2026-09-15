import React from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import './index.css';
import { AuthProvider } from '@/contexts/AuthContext';
import { AppLayout } from '@/components/layout/AppLayout';
import { ProtectedRoute } from '@/components/auth/ProtectedRoute';
import { ControlTower } from '@/pages/ControlTower';
import { DisruptionDetail } from '@/pages/DisruptionDetail';
import { ShipmentDetail } from '@/pages/ShipmentDetail';
import { RerouteWorkbench } from '@/pages/RerouteWorkbench';
import { FleetPage } from '@/pages/FleetPage';
import { ColdChainMonitor } from '@/pages/ColdChainMonitor';
import { LandingPage } from '@/pages/LandingPage';
import { LoginPage } from '@/pages/LoginPage';
import { SignupPage } from '@/pages/SignupPage';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            {/* Public routes */}
            <Route path="/" element={<LandingPage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/signup" element={<SignupPage />} />

            {/* Gated routes — ProtectedRoute handles loading/anon */}
            <Route element={<ProtectedRoute />}>
              <Route element={<AppLayout />}>
                <Route path="/tower" element={<ControlTower />} />
                <Route path="/tower/disruptions/:id" element={<DisruptionDetail />} />
                <Route path="/tower/shipments/:id" element={<ShipmentDetail />} />
                <Route path="/tower/reroutes" element={<RerouteWorkbench />} />
                <Route path="/tower/fleet" element={<FleetPage />} />
                <Route path="/tower/cold-chain" element={<ColdChainMonitor />} />
              </Route>
            </Route>
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>
);
