"use client";

import { useEffect, useState } from "react";
import {
  GeoJSON,
  MapContainer,
  TileLayer,
  useMap,
} from "react-leaflet";
import type { FeatureCollection } from "geojson";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

function FitBounds({ data }: { data: FeatureCollection }) {
  const map = useMap();

  useEffect(() => {
    const layer = L.geoJSON(data);
    const bounds = layer.getBounds();

    if (bounds.isValid()) {
      map.fitBounds(bounds, { padding: [20, 20] });
    }
  }, [data, map]);

  return null;
}

export default function BhopalWardMap() {
  const [data, setData] = useState<FeatureCollection | null>(null);

  useEffect(() => {
    fetch("/geo/Bhopal_wards.geojson")
      .then((res) => res.json())
      .then(setData)
      .catch((err) => console.error("GeoJSON load failed:", err));
  }, []);

  if (!data) {
    return <div className="map-loading">Loading Bhopal map...</div>;
  }

  return (
    <div style={{ height: "600px", width: "100%" }}>
      <MapContainer
        center={[23.2599, 77.4126]}
        zoom={11}
        style={{ height: "100%", width: "100%" }}
      >
        <TileLayer
          attribution="&copy; OpenStreetMap contributors"
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        <FitBounds data={data} />

        <GeoJSON
          data={data}
          style={() => ({
            color: "#2563eb",
            weight: 1.5,
            fillOpacity: 0.15,
          })}
          onEachFeature={(feature, layer) => {
            const p = feature.properties;

            layer.bindPopup(`
              <strong>Ward ${p?.Ward_Number ?? "N/A"}</strong><br/>
              ${p?.Name ?? "Unknown"}<br/>
              Zone: ${p?.zone ?? "N/A"}<br/>
              Population: ${p?.population ?? "N/A"}
            `);
          }}
        />
      </MapContainer>
    </div>
  );
}