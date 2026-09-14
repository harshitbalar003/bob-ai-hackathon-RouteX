/**
 * TanStack Query hooks — all data access goes through these.
 * Components never call adapter methods directly.
 */
import { useQuery } from '@tanstack/react-query';
import { adapter } from '@/lib/adapter';

const STALE_TIME = 30_000; // 30 s

export function useDisruptions() {
  return useQuery({
    queryKey: ['disruptions'],
    queryFn: () => adapter.getDisruptions(),
    staleTime: STALE_TIME,
  });
}

export function useDisruption(id: string) {
  return useQuery({
    queryKey: ['disruption', id],
    queryFn: () => adapter.getDisruption(id),
    staleTime: STALE_TIME,
    enabled: !!id,
  });
}

export function useShipments() {
  return useQuery({
    queryKey: ['shipments'],
    queryFn: () => adapter.getShipments(),
    staleTime: STALE_TIME,
  });
}

export function useShipment(id: string) {
  return useQuery({
    queryKey: ['shipment', id],
    queryFn: () => adapter.getShipment(id),
    staleTime: STALE_TIME,
    enabled: !!id,
  });
}

export function useShipmentsByDisruption(disruptionId: string) {
  return useQuery({
    queryKey: ['shipments-by-disruption', disruptionId],
    queryFn: () => adapter.getShipmentsByDisruption(disruptionId),
    staleTime: STALE_TIME,
    enabled: !!disruptionId,
  });
}

export function useRerouteOptions(shipmentId: string) {
  return useQuery({
    queryKey: ['reroutes', shipmentId],
    queryFn: () => adapter.getRerouteOptions(shipmentId),
    staleTime: STALE_TIME,
    enabled: !!shipmentId,
  });
}

export function useAllRerouteOptions() {
  return useQuery({
    queryKey: ['reroutes-all'],
    queryFn: () => adapter.getAllRerouteOptions(),
    staleTime: STALE_TIME,
  });
}

export function useFleetAssets() {
  return useQuery({
    queryKey: ['fleet'],
    queryFn: () => adapter.getFleetAssets(),
    staleTime: STALE_TIME,
  });
}

export function useRedeploymentMatches() {
  return useQuery({
    queryKey: ['redeployment-matches'],
    queryFn: () => adapter.getRedeploymentMatches(),
    staleTime: STALE_TIME,
  });
}

export function useSensorReadings(shipmentId: string) {
  return useQuery({
    queryKey: ['sensor-readings', shipmentId],
    queryFn: () => adapter.getSensorReadings(shipmentId),
    staleTime: STALE_TIME,
    enabled: !!shipmentId,
  });
}

export function useSensorGaps(shipmentId: string) {
  return useQuery({
    queryKey: ['sensor-gaps', shipmentId],
    queryFn: () => adapter.getSensorGaps(shipmentId),
    staleTime: STALE_TIME,
    enabled: !!shipmentId,
  });
}

export function useExcursions() {
  return useQuery({
    queryKey: ['excursions'],
    queryFn: () => adapter.getExcursions(),
    staleTime: STALE_TIME,
  });
}

export function useExcursion(id: string) {
  return useQuery({
    queryKey: ['excursion', id],
    queryFn: () => adapter.getExcursion(id),
    staleTime: STALE_TIME,
    enabled: !!id,
  });
}

export function usePriorityQueue() {
  return useQuery({
    queryKey: ['priority-queue'],
    queryFn: () => adapter.getPriorityQueue(),
    staleTime: STALE_TIME,
    refetchInterval: 60_000, // refresh every minute
  });
}
