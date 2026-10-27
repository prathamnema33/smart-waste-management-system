"use client";

import { useEffect, useMemo } from "react";
import { CircleMarker, MapContainer, Popup, TileLayer, useMap } from "react-leaflet";
import type { MonitoringDashboardData, MonitoringMapMarker } from "@/lib/types";
import "leaflet/dist/leaflet.css";

const markerTypes = [
  { key: "vehicles", label: "Vehicle", color: "#2563eb" },
  { key: "waste_reports", label: "Waste report", color: "#d69b22" },
  { key: "collections", label: "Collection", color: "#087f72" },
  { key: "alerts", label: "Alert", color: "#d34e42" },
] as const;

type MapLocations = MonitoringDashboardData["map_locations"];

function MapViewport({ points }: { points: [number, number][] }) {
  const map = useMap();
  useEffect(() => {
    if (points.length > 1) {
      map.fitBounds(points, { padding: [28, 28], maxZoom: 13 });
    } else if (points.length === 1) {
      map.setView(points[0], 13);
    }
  }, [map, points]);
  return null;
}

function MapMarker({
  marker,
  color,
}: {
  marker: MonitoringMapMarker;
  color: string;
}) {
  return (
    <CircleMarker
      center={[marker.latitude, marker.longitude]}
      radius={marker.status === "CRITICAL" ? 9 : 6}
      pathOptions={{ color, fillColor: color, fillOpacity: 0.78, weight: 2 }}
    >
      <Popup>
        <div className="monitoring-popup">
          <strong>{marker.label}</strong>
          {marker.status && <span>Status: {marker.status.replaceAll("_", " ")}</span>}
          {marker.detail && <span>{marker.detail}</span>}
          {marker.created_at && <span>{new Date(marker.created_at).toLocaleString()}</span>}
          <span>{marker.latitude.toFixed(6)}, {marker.longitude.toFixed(6)}</span>
        </div>
      </Popup>
    </CircleMarker>
  );
}

export default function MonitoringMap({ locations }: { locations: MapLocations }) {
  const points = useMemo(
    () =>
      markerTypes.flatMap(({ key }) =>
        locations[key].map((marker) => [marker.latitude, marker.longitude] as [number, number]),
      ),
    [locations],
  );
  const center = useMemo<[number, number]>(
    () => [
      points.reduce((total, [latitude]) => total + latitude, 0) / points.length,
      points.reduce((total, [, longitude]) => total + longitude, 0) / points.length,
    ],
    [points],
  );

  return (
    <MapContainer center={center} zoom={11} scrollWheelZoom className="monitoring-map-canvas">
      <MapViewport points={points} />
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      {markerTypes.flatMap(({ key, color }) =>
        locations[key].map((marker) => (
          <MapMarker key={`${key}-${marker.id}`} marker={marker} color={color} />
        )),
      )}
    </MapContainer>
  );
}
