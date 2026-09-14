import React, { useMemo, useCallback } from 'react';
import * as d3geo from 'd3-geo';
import { feature } from 'topojson-client';
import type { Topology, GeometryCollection } from 'topojson-specification';
import type { Shipment, Disruption, FleetAsset, Severity } from '@/types/domain';
import { useUIStore } from '@/lib/store';
import { useNavigate } from 'react-router-dom';
import worldTopo from 'world-atlas/land-110m.json';

interface WorldMapProps {
  shipments: Shipment[];
  disruptions: Disruption[];
  assets: FleetAsset[];
}

const WIDTH = 800;
const HEIGHT = 420;

const SEVERITY_STROKE: Record<Severity, string> = {
  informational: '#5b9cf6',
  minor: '#5b9cf6',
  major: '#e8a03a',
  critical: '#e84040',
};

const SEVERITY_FILL: Record<Severity, string> = {
  informational: '#5b9cf6',
  minor: '#5b9cf6',
  major: '#e8a03a',
  critical: '#e84040',
};

const STATUS_STROKE: Record<string, string> = {
  on_track: '#3ab8c8',
  at_risk: '#e8a03a',
  delayed: '#e8a03a',
  exception: '#e84040',
};

const MODE_DASH: Record<string, string> = {
  ocean: '',
  air: '5,3',
  road: '3,2',
  rail: '7,2,2,2',
};

export function WorldMap({ shipments, disruptions, assets }: WorldMapProps) {
  const { mapLayerRoutes, mapLayerZones, mapLayerAssets } = useUIStore();
  const navigate = useNavigate();

  const projection = useMemo(
    () =>
      d3geo
        .geoNaturalEarth1()
        .scale(130)
        .translate([WIDTH / 2, HEIGHT / 2 + 24]),
    [],
  );

  const pathGen = useMemo(() => d3geo.geoPath().projection(projection), [projection]);

  // Land polygons from bundled TopoJSON — renders fully offline
  const landPath = useMemo(() => {
    const land = feature(
      worldTopo as Topology<{ land: GeometryCollection }>,
      worldTopo.objects.land as GeometryCollection,
    );
    return pathGen(land) ?? '';
  }, [pathGen]);

  // Graticule
  const graticule = useMemo(() => {
    const gen = d3geo.geoGraticule()();
    return pathGen(gen) ?? '';
  }, [pathGen]);

  // Sphere (ocean background outline)
  const sphere = useMemo(() => pathGen({ type: 'Sphere' }) ?? '', [pathGen]);

  // Project helper — returns null if outside projection bounds
  const project = useCallback(
    (lat: number, lng: number): [number, number] | null => projection([lng, lat]),
    [projection],
  );

  // Pre-compute arc paths for visible shipments
  const arcs = useMemo(() => {
    if (!mapLayerRoutes) return [];
    return shipments
      .filter((s) => s.origin && s.destination)
      .map((s) => {
        const from = project(s.origin.lat, s.origin.lng);
        const to = project(s.destination.lat, s.destination.lng);
        if (!from || !to) return null;

        // Great-circle arc via d3geo interpolation (5 intermediate points)
        const interp = d3geo.geoInterpolate(
          [s.origin.lng, s.origin.lat],
          [s.destination.lng, s.destination.lat],
        );
        const pts = [0, 0.2, 0.4, 0.6, 0.8, 1].map((t) => {
          const [lng, lat] = interp(t);
          return projection([lng, lat]);
        });

        // Build SVG path through projected points
        const valid = pts.filter((p): p is [number, number] => p !== null);
        if (valid.length < 2) return null;

        const d = valid
          .map((p, i) => `${i === 0 ? 'M' : 'L'}${p[0].toFixed(1)},${p[1].toFixed(1)}`)
          .join(' ');

        const stroke = STATUS_STROKE[s.status] ?? '#3ab8c8';
        const dash = MODE_DASH[s.legs[0]?.mode ?? 'ocean'];
        const isException = s.status === 'exception';

        return { id: s.id, d, stroke, dash, isException };
      })
      .filter(Boolean);
  }, [shipments, mapLayerRoutes, project, projection]);

  // Pre-compute disruption zone circles
  const zones = useMemo(() => {
    if (!mapLayerZones) return [];
    return disruptions.map((dis) => {
      const area = dis.affectedArea as
        | { center: { lat: number; lng: number }; radiusKm: number }
        | { polygon: [number, number][] };

      if ('center' in area) {
        const pt = project(area.center.lat, area.center.lng);
        if (!pt) return null;
        // Approximate radius in SVG pixels: 1 degree ≈ 111km, scale ≈ 130/6371*px
        const radiusPx = (area.radiusKm / 111) * (130 / 57.3);
        return {
          id: dis.id,
          kind: 'circle' as const,
          cx: pt[0],
          cy: pt[1],
          r: Math.max(8, radiusPx),
          severity: dis.severity,
          headline: dis.headline,
        };
      }
      return null;
    }).filter(Boolean);
  }, [disruptions, mapLayerZones, project]);

  // Idle asset cluster dots
  const assetDots = useMemo(() => {
    if (!mapLayerAssets) return [];
    return assets
      .filter((a) => a.status === 'idle')
      .map((a) => {
        const pt = project(a.location.lat, a.location.lng);
        if (!pt) return null;
        return { id: a.id, cx: pt[0], cy: pt[1], reefer: a.reeferCapable };
      })
      .filter(Boolean);
  }, [assets, mapLayerAssets, project]);

  return (
    <svg
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      className="w-full h-full"
      aria-label="World map showing shipment routes, disruption zones, and idle fleet assets"
      role="img"
    >
      <defs>
        <clipPath id="map-clip">
          <path d={sphere} />
        </clipPath>
      </defs>

      {/* Ocean */}
      <path d={sphere} fill="#0a1118" />

      {/* Graticule grid */}
      <path
        d={graticule}
        fill="none"
        stroke="#1a2840"
        strokeWidth="0.4"
        clipPath="url(#map-clip)"
      />

      {/* Land masses */}
      <path
        d={landPath}
        fill="#162032"
        stroke="#263350"
        strokeWidth="0.6"
        clipPath="url(#map-clip)"
      />

      {/* Disruption zones */}
      {zones.map((z) => {
        if (!z || z.kind !== 'circle') return null;
        const stroke = SEVERITY_STROKE[z.severity as Severity] ?? '#e8a03a';
        const fill = SEVERITY_FILL[z.severity as Severity] ?? '#e8a03a';
        return (
          <g key={z.id} clipPath="url(#map-clip)">
            <circle
              cx={z.cx}
              cy={z.cy}
              r={z.r}
              fill={fill}
              fillOpacity={0.1}
              stroke={stroke}
              strokeWidth={1}
              strokeOpacity={0.55}
              strokeDasharray="4,2"
            />
            <circle
              cx={z.cx}
              cy={z.cy}
              r={3}
              fill={stroke}
              fillOpacity={0.8}
            />
          </g>
        );
      })}

      {/* Shipment arcs */}
      {arcs.map((arc) => {
        if (!arc) return null;
        return (
          <path
            key={arc.id}
            d={arc.d}
            fill="none"
            stroke={arc.stroke}
            strokeWidth={arc.isException ? 1.6 : 0.9}
            strokeOpacity={arc.isException ? 0.92 : 0.42}
            strokeDasharray={arc.dash}
            clipPath="url(#map-clip)"
            className="cursor-pointer"
            onClick={() => navigate(`/shipments/${arc.id}`)}
          >
            <title>{arc.id}</title>
          </path>
        );
      })}

      {/* Fleet asset dots */}
      {assetDots.map((dot) => {
        if (!dot) return null;
        return (
          <circle
            key={dot.id}
            cx={dot.cx}
            cy={dot.cy}
            r={dot.reefer ? 4 : 3}
            fill={dot.reefer ? '#3ab8c8' : '#7e94b4'}
            fillOpacity={0.65}
            stroke={dot.reefer ? '#3ab8c8' : 'none'}
            strokeWidth={dot.reefer ? 0.8 : 0}
            strokeOpacity={0.4}
            clipPath="url(#map-clip)"
          >
            <title>{dot.id} — idle{dot.reefer ? ' · ❄ reefer' : ''}</title>
          </circle>
        );
      })}

      {/* Map legend */}
      <g transform={`translate(8, ${HEIGHT - 72})`}>
        <rect x={-4} y={-4} width={148} height={76} rx={3}
          fill="#0e1621" fillOpacity={0.85} stroke="#263350" strokeWidth={0.7} />
        {[
          { x: 4, y: 10, stroke: '#3ab8c8', dash: '', label: 'On track (ocean)' },
          { x: 4, y: 22, stroke: '#e8a03a', dash: '5,3', label: 'At risk / air' },
          { x: 4, y: 34, stroke: '#e84040', dash: '', label: 'Exception' },
          { x: 4, y: 46, stroke: '#e8a03a', dash: '4,2', label: 'Disruption zone', circle: true },
          { x: 4, y: 58, stroke: '#3ab8c8', dot: true, label: 'Idle reefer asset' },
        ].map(({ x, y, stroke, dash, label, circle, dot }) => (
          <g key={label}>
            {circle ? (
              <circle cx={x + 10} cy={y} r={5} fill={stroke} fillOpacity={0.12}
                stroke={stroke} strokeWidth={1} strokeDasharray="3,1.5" />
            ) : dot ? (
              <circle cx={x + 10} cy={y} r={3} fill={stroke} fillOpacity={0.7} />
            ) : (
              <line x1={x} y1={y} x2={x + 20} y2={y}
                stroke={stroke} strokeWidth={1.5} strokeDasharray={dash} />
            )}
            <text x={x + 26} y={y + 4} fill="#7e94b4" fontSize={9}>{label}</text>
          </g>
        ))}
      </g>
    </svg>
  );
}
