import { create } from 'zustand';

interface UIState {
  selectedDisruptionId: string | null;
  selectedShipmentId: string | null;
  mapLayerRoutes: boolean;
  mapLayerZones: boolean;
  mapLayerAssets: boolean;
  setSelectedDisruption: (id: string | null) => void;
  setSelectedShipment: (id: string | null) => void;
  toggleMapLayer: (layer: 'routes' | 'zones' | 'assets') => void;
}

export const useUIStore = create<UIState>((set) => ({
  selectedDisruptionId: null,
  selectedShipmentId: null,
  mapLayerRoutes: true,
  mapLayerZones: true,
  mapLayerAssets: true,
  setSelectedDisruption: (id) => set({ selectedDisruptionId: id }),
  setSelectedShipment: (id) => set({ selectedShipmentId: id }),
  toggleMapLayer: (layer) =>
    set((state) => {
      if (layer === 'routes') return { mapLayerRoutes: !state.mapLayerRoutes };
      if (layer === 'zones') return { mapLayerZones: !state.mapLayerZones };
      return { mapLayerAssets: !state.mapLayerAssets };
    }),
}));
