import React from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import './index.css';
import { AppLayout } from '@/components/layout/AppLayout';
import { ControlTower } from '@/pages/ControlTower';
import { DisruptionDetail } from '@/pages/DisruptionDetail';
import { ShipmentDetail } from '@/pages/ShipmentDetail';
import { RerouteWorkbench } from '@/pages/RerouteWorkbench';
import { FleetPage } from '@/pages/FleetPage';
import { ColdChainMonitor } from '@/pages/ColdChainMonitor';

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
        <Routes>
          <Route element={<AppLayout />}>
            <Route index element={<ControlTower />} />
            <Route path="/disruptions/:id" element={<DisruptionDetail />} />
            <Route path="/shipments/:id" element={<ShipmentDetail />} />
            <Route path="/reroutes" element={<RerouteWorkbench />} />
            <Route path="/fleet" element={<FleetPage />} />
            <Route path="/cold-chain" element={<ColdChainMonitor />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>
);
