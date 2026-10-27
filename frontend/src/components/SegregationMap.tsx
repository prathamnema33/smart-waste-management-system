"use client";

import { useEffect, useMemo } from "react";
import { CircleMarker, MapContainer, Polygon, Popup, TileLayer, useMap } from "react-leaflet";
import type { AreaSegregation, Team } from "@/lib/types";

export const SEGREGATION_THRESHOLDS = {
  good: 80,
  needsImprovement: 60,
} as const;

const statusFor = (score: number) => {
  if (score >= SEGREGATION_THRESHOLDS.good) {
    return { label: "Good", color: "#2f8c56" };
  }
  if (score >= SEGREGATION_THRESHOLDS.needsImprovement) {
    return { label: "Needs Improvement", color: "#d6a126" };
  }
  return { label: "Poor", color: "#c65b50" };
};

function hasCoordinates(area: AreaSegregation): area is AreaSegregation & {
  latitude: number;
  longitude: number;
} {
  return (
    typeof area.latitude === "number" &&
    Number.isFinite(area.latitude) &&
    area.latitude >= -90 &&
    area.latitude <= 90 &&
    typeof area.longitude === "number" &&
    Number.isFinite(area.longitude) &&
    area.longitude >= -180 &&
    area.longitude <= 180
  );
}

function AreaMarker({ area }: { area: AreaSegregation & { latitude: number; longitude: number } }) {
  const status = statusFor(area.segregation_score);
  const radius = Math.min(18, 8 + Math.sqrt(area.total_ratings));

  return (
    <CircleMarker
      center={[area.latitude, area.longitude]}
      radius={radius}
      pathOptions={{
        color: status.color,
        fillColor: status.color,
        fillOpacity: 0.72,
        weight: 2,
      }}
    >
      <Popup>
        <div className="segregation-popup">
          <h3>{area.area_name}</h3>
          <strong>Segregation Score: {area.segregation_score.toFixed(1)}%</strong>
          <p>Status: {status.label}</p>
          <p>Average Rating: {area.average_rating.toFixed(1)} / 5</p>
          <p>Total Ratings: {area.total_ratings.toLocaleString()}</p>
          <div className="segregation-popup-breakdown">
            <span>Excellent: {area.excellent_ratings.toLocaleString()}</span>
            <span>Good: {area.good_ratings.toLocaleString()}</span>
            <span>Average: {area.average_ratings.toLocaleString()}</span>
            <span>Poor: {area.poor_ratings.toLocaleString()}</span>
          </div>
        </div>
      </Popup>
    </CircleMarker>
  );
}

function TeamZone({ team }: { team: Team & { zone_boundary: [number, number][] } }) {
  return (
    <Polygon
      positions={team.zone_boundary}
      pathOptions={{
        color: "#075c55",
        fillColor: "#087f72",
        fillOpacity: 0.14,
        weight: 2,
      }}
    >
      <Popup>
        <div className="segregation-popup">
          <h3>{team.team_name}</h3>
          <p>Area: {team.area_name}</p>
          <p>Leader: {team.leader_name}</p>
          <p>Workers: {team.worker_count}</p>
          <p>Vehicle: {team.vehicle_number ?? "Not assigned"}</p>
          <div className="segregation-popup-breakdown">
            <span>South: {team.min_latitude?.toFixed(6) ?? "—"}</span>
            <span>North: {team.max_latitude?.toFixed(6) ?? "—"}</span>
            <span>West: {team.min_longitude?.toFixed(6) ?? "—"}</span>
            <span>East: {team.max_longitude?.toFixed(6) ?? "—"}</span>
          </div>
        </div>
      </Popup>
    </Polygon>
  );
}

function MapSizeInvalidator({ visible }: { visible: boolean }) {
  const map = useMap();

  useEffect(() => {
    if (visible) map.invalidateSize();
  }, [map, visible]);

  return null;
}

function MapViewportSync({ points }: { points: [number, number][] }) {
  const map = useMap();

  useEffect(() => {
    if (points.length > 1) {
      map.fitBounds(points, { padding: [28, 28], maxZoom: 12 });
    } else if (points.length === 1) {
      map.setView(points[0], 12);
    }
  }, [map, points]);

  return null;
}

export default function SegregationMap({
  areas,
  teams,
  visible,
}: {
  areas: AreaSegregation[];
  teams: Team[];
  visible: boolean;
}) {
  const plottedAreas = useMemo(() => areas.filter(hasCoordinates), [areas]);
  const plottedTeams = useMemo(
    () =>
      teams.filter(
        (team): team is Team & { zone_boundary: [number, number][] } =>
          team.zone_boundary !== null && team.zone_boundary.length >= 3,
      ),
    [teams],
  );
  const mapPoints = useMemo(
    () => [
      ...plottedAreas.map((area) => [area.latitude, area.longitude] as [number, number]),
      ...plottedTeams.flatMap((team) => team.zone_boundary),
    ],
    [plottedAreas, plottedTeams],
  );
  if (mapPoints.length === 0) {
    return (
      <div className="empty-state segregation-map-empty">
        No areas or team zones have valid map coordinates.
      </div>
    );
  }

  const center: [number, number] = [
    mapPoints.reduce((sum, [latitude]) => sum + latitude, 0) / mapPoints.length,
    mapPoints.reduce((sum, [, longitude]) => sum + longitude, 0) / mapPoints.length,
  ];

  return (
    <>
      {(plottedAreas.length !== areas.length || plottedTeams.length !== teams.length) && (
        <p className="segregation-map-note">
          Areas without valid coordinates and teams without a boundary are not plotted.
        </p>
      )}
      <MapContainer
        center={center}
        zoom={mapPoints.length === 1 ? 12 : 10}
        scrollWheelZoom
        className="segregation-map-canvas"
      >
        <MapSizeInvalidator visible={visible} />
        <MapViewportSync points={mapPoints} />
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {plottedAreas.map((area) => (
          <AreaMarker key={area.area_id} area={area} />
        ))}
        {plottedTeams.map((team) => (
          <TeamZone key={team.team_id} team={team} />
        ))}
      </MapContainer>
      <div className="segregation-map-legend" aria-label="Segregation map legend">
        {plottedTeams.length > 0 && (
          <span>
            <i className="team-zone" /> Team zone boundary
          </span>
        )}
        <span>
          <i className="good" /> Green — Good ≥ {SEGREGATION_THRESHOLDS.good}%
        </span>
        <span>
          <i className="medium" /> Yellow — Medium {SEGREGATION_THRESHOLDS.needsImprovement}–
          {SEGREGATION_THRESHOLDS.good - 0.01}%
        </span>
        <span>
          <i className="poor" /> Red — Poor &lt; {SEGREGATION_THRESHOLDS.needsImprovement}%
        </span>
      </div>
    </>
  );
}
