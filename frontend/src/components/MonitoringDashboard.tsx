"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type {
  MonitoringAlert,
  MonitoringDashboardData,
  MonitoringMapMarker,
  MonitoringPendingRequest,
  MonitoringVehicle,
  MonitoringWard,
} from "@/lib/types";
import "./monitoring.css";

const MonitoringMap = dynamic(() => import("./MonitoringMap"), {
  ssr: false,
  loading: () => <div className="monitoring-map-state">Loading live map...</div>,
});

const REFRESH_INTERVAL_MS = 45_000;

function formatNumber(value: number, digits = 0) {
  return new Intl.NumberFormat("en-IN", { maximumFractionDigits: digits }).format(value);
}

function formatDateTime(value: string | null) {
  if (!value) return "Not available";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? "Not available"
    : parsed.toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });
}

function formatDuration(value: string | null) {
  if (!value) return "—";
  const elapsedMinutes = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 60_000));
  if (!Number.isFinite(elapsedMinutes)) return "—";
  if (elapsedMinutes < 60) return `${elapsedMinutes}m`;
  const hours = Math.floor(elapsedMinutes / 60);
  if (hours < 24) return `${hours}h ${elapsedMinutes % 60}m`;
  return `${Math.floor(hours / 24)}d ${hours % 24}h`;
}

function displayStatus(value: string | null | undefined) {
  return value ? value.replaceAll("_", " ") : "Not reported";
}

function MonitoringMetric({
  title,
  value,
  detail,
  tone = "teal",
}: {
  title: string;
  value: string;
  detail: string;
  tone?: string;
}) {
  return (
    <div className={`metric-card ${tone}`}>
      <span className="metric-label">{title}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}

function PanelTitle({
  eyebrow,
  title,
  detail,
}: {
  eyebrow: string;
  title: string;
  detail?: string;
}) {
  return (
    <div className="section-title">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h2>{title}</h2>
        {detail && <p className="muted monitoring-panel-detail">{detail}</p>}
      </div>
    </div>
  );
}

function StatusBreakdown({
  label,
  count,
  total,
  tone,
}: {
  label: string;
  count: number;
  total: number;
  tone: string;
}) {
  const percentage = total > 0 ? (count / total) * 100 : 0;
  return (
    <div className="monitoring-status-row">
      <div className="monitoring-status-heading">
        <span><i className={`monitoring-status-dot ${tone}`} />{label}</span>
        <strong>{formatNumber(count)} <small>{percentage.toFixed(1)}%</small></strong>
      </div>
      <div
        className="monitoring-progress-track"
        role="progressbar"
        aria-label={`${label} share of collection requests`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Number(percentage.toFixed(1))}
      >
        <span className={tone} style={{ width: `${percentage}%` }} />
      </div>
    </div>
  );
}

function VehicleTable({ vehicles }: { vehicles: MonitoringVehicle[] }) {
  if (vehicles.length === 0) {
    return <div className="monitoring-empty">No vehicles are registered for monitoring.</div>;
  }
  return (
    <div className="table-wrap">
      <table className="monitoring-table">
        <thead>
          <tr>
            <th>Vehicle</th>
            <th>Last known location</th>
            <th>Worker / team</th>
            <th>Collection</th>
            <th>Last GPS update</th>
          </tr>
        </thead>
        <tbody>
          {vehicles.map((vehicle) => (
            <tr key={vehicle.vehicle_id}>
              <td>
                <strong>{vehicle.vehicle_number}</strong>
                <small>{displayStatus(vehicle.vehicle_status)}</small>
              </td>
              <td>
                <strong>{vehicle.area_name ?? "Area not assigned"}</strong>
                <small>
                  {vehicle.ward_name
                    ? `${vehicle.ward_name}${vehicle.ward_number ? ` · Ward ${vehicle.ward_number}` : ""}`
                    : "Ward not assigned"}
                  {vehicle.latitude !== null && vehicle.longitude !== null
                    ? ` · ${vehicle.latitude.toFixed(4)}, ${vehicle.longitude.toFixed(4)}`
                    : " · Location unavailable"}
                </small>
              </td>
              <td>
                <strong>{vehicle.worker_name ?? `Worker #${vehicle.worker_id}`}</strong>
                <small>{vehicle.team_name ?? "Team not assigned"}</small>
              </td>
              <td><span className={`status ${vehicle.collection_status?.toLowerCase() ?? ""}`}>{displayStatus(vehicle.collection_status)}</span></td>
              <td>{formatDateTime(vehicle.last_gps_update)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AlertList({ alerts }: { alerts: MonitoringAlert[] }) {
  if (alerts.length === 0) {
    return <div className="monitoring-empty">There are no alerts to display.</div>;
  }
  return (
    <div className="monitoring-alert-list">
      {alerts.slice(0, 8).map((alert) => (
        <article className="monitoring-alert" key={alert.alert_id}>
          <span className={`severity ${alert.severity?.toLowerCase() ?? ""}`}>
            {alert.severity ?? "UNRATED"}
          </span>
          <div className="monitoring-alert-copy">
            <div className="monitoring-alert-heading">
              <strong>{displayStatus(alert.alert_type)}</strong>
              <span className={`status ${alert.status?.toLowerCase() ?? "open"}`}>
                {displayStatus(alert.status)}
              </span>
            </div>
            <p>{alert.message}</p>
            <small>
              {alert.ward_name ?? alert.area_name ?? "Area unavailable"} · {formatDateTime(alert.created_at)}
            </small>
          </div>
        </article>
      ))}
    </div>
  );
}

function PendingTable({ requests }: { requests: MonitoringPendingRequest[] }) {
  if (requests.length === 0) {
    return <div className="monitoring-empty">No assigned or in-progress collections are pending.</div>;
  }
  return (
    <div className="table-wrap">
      <table className="monitoring-table">
        <thead>
          <tr>
            <th>Request</th>
            <th>Ward / area</th>
            <th>Worker</th>
            <th>Vehicle</th>
            <th>Status</th>
            <th>Requested</th>
            <th>Waiting</th>
          </tr>
        </thead>
        <tbody>
          {requests.map((request) => (
            <tr key={request.request_id}>
              <td><strong>#{request.request_id}</strong><small>Report #{request.report_id}</small></td>
              <td>
                <strong>{request.ward_name ?? "Ward unavailable"}</strong>
                <small>{request.area_name ?? "Area unavailable"}</small>
              </td>
              <td>{request.worker_name ?? "Not assigned"}</td>
              <td>{request.vehicle_number ?? "Not assigned"}</td>
              <td><span className={`status ${request.status.toLowerCase()}`}>{displayStatus(request.status)}</span></td>
              <td>{formatDateTime(request.requested_at)}</td>
              <td><strong>{formatDuration(request.requested_at)}</strong></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function WardAttention({ wards }: { wards: MonitoringWard[] }) {
  const priorityWards = wards.filter((ward) => ward.attention_reasons.length > 0).slice(0, 12);
  if (priorityWards.length === 0) {
    return <div className="monitoring-empty">No wards currently meet the attention thresholds.</div>;
  }
  return (
    <div className="table-wrap">
      <table className="monitoring-table monitoring-ward-table">
        <thead>
          <tr>
            <th>Ward</th>
            <th>Attention drivers</th>
            <th>Pending</th>
            <th>Waste</th>
            <th>Collection efficiency</th>
            <th>Open complaints</th>
            <th>Alerts</th>
          </tr>
        </thead>
        <tbody>
          {priorityWards.map((ward) => (
            <tr key={ward.ward_id}>
              <td>
                <strong>{ward.ward_name}</strong>
                <small>Ward {ward.ward_number}</small>
              </td>
              <td>
                <span className={`monitoring-attention ${ward.attention_level.toLowerCase()}`}>
                  {ward.attention_level}
                </span>
                <small className="monitoring-reasons">{ward.attention_reasons.join(" · ")}</small>
              </td>
              <td>{formatNumber(ward.pending_collections)}</td>
              <td>{formatNumber(ward.total_waste_kg, 1)} kg</td>
              <td>{formatNumber(ward.collection_efficiency, 1)}%</td>
              <td>{formatNumber(ward.open_complaints)}</td>
              <td>{formatNumber(ward.unresolved_alerts)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MonitoringMapPanel({
  locations,
}: {
  locations: MonitoringDashboardData["map_locations"];
}) {
  const pointCount = Object.values(locations).reduce((sum, markers) => sum + markers.length, 0);
  return (
    <section className="panel monitoring-map-panel">
      <PanelTitle
        eyebrow="Live geography"
        title="Vehicles, collections & alerts"
        detail={`${formatNumber(pointCount)} stored locations with valid coordinates`}
      />
      {pointCount > 0
        ? (
          <>
            <MonitoringMap locations={locations} />
            <div className="monitoring-map-legend" aria-label="Map marker legend">
              <MarkerLegend label="Vehicles" markers={locations.vehicles} />
              <MarkerLegend label="Waste reports" markers={locations.waste_reports} />
              <MarkerLegend label="Collections" markers={locations.collections} />
              <MarkerLegend label="Alerts" markers={locations.alerts} />
            </div>
          </>
        )
        : <div className="monitoring-empty">No stored vehicle, report, collection, or alert coordinates are available.</div>}
    </section>
  );
}

function MarkerLegend({ label, markers }: { label: string; markers: MonitoringMapMarker[] }) {
  return (
    <span className="monitoring-legend-item">
      <i className={`monitoring-map-dot ${label.toLowerCase().replaceAll(" ", "-")}`} />
      {label} <small>{formatNumber(markers.length)}</small>
    </span>
  );
}

export default function MonitoringDashboard() {
  const [data, setData] = useState<MonitoringDashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const inFlight = useRef(false);
  const hasLoaded = useRef(false);

  const refresh = useCallback(async (manual = false) => {
    if (inFlight.current) return;
    inFlight.current = true;
    if (hasLoaded.current) {
      if (manual) setRefreshing(true);
    } else {
      setLoading(true);
    }
    try {
      const nextData = await api.monitoring();
      setData(nextData);
      setLastUpdated(nextData.updated_at);
      setError(null);
      hasLoaded.current = true;
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to load monitoring data.");
    } finally {
      setLoading(false);
      setRefreshing(false);
      inFlight.current = false;
    }
  }, []);

  useEffect(() => {
    const initialRefresh = window.setTimeout(() => void refresh(), 0);
    const timer = window.setInterval(() => void refresh(), REFRESH_INTERVAL_MS);
    return () => {
      window.clearTimeout(initialRefresh);
      window.clearInterval(timer);
    };
  }, [refresh]);

  if (loading && !data) {
    return <div className="loading-line"><div className="spinner" />Loading monitoring data...</div>;
  }
  if (error && !data) {
    return (
      <div className="monitoring-error" role="alert">
        <div><strong>Monitoring data could not be loaded.</strong><p>{error}</p></div>
        <button className="outline-button" onClick={() => void refresh(true)}>Try again</button>
      </div>
    );
  }
  if (!data) return null;

  const summary = data.summary;
  const updatedText = lastUpdated ? formatDateTime(lastUpdated) : "Not yet updated";
  const mapLocations = data.map_locations;

  return (
    <div className="monitoring-dashboard">
      <div className="monitoring-toolbar">
        <div>
          <span className="monitoring-live-indicator"><i />LIVE MONITORING</span>
          <p>Last updated <strong>{updatedText}</strong> · refreshes every 45 seconds</p>
        </div>
        <button className="outline-button" disabled={refreshing} onClick={() => void refresh(true)}>
          {refreshing ? "Updating..." : "↻ Refresh now"}
        </button>
      </div>
      {error && <div className="monitoring-stale-warning" role="status">Refresh failed: {error}. Showing the last successful update.</div>}

      <div className="metric-grid monitoring-metrics">
        <MonitoringMetric title="Active requests" value={formatNumber(summary.active_requests)} detail="Assigned + in progress" />
        <MonitoringMetric title="In progress" value={formatNumber(summary.in_progress)} detail="Collections underway" tone="amber" />
        <MonitoringMetric title="Assigned" value={formatNumber(summary.assigned)} detail="Awaiting collection" />
        <MonitoringMetric title="Collected" value={formatNumber(summary.collected)} detail={`${formatNumber(summary.collection_efficiency, 1)}% of all requests`} tone="lime" />
        <MonitoringMetric title="Unresolved alerts" value={formatNumber(summary.unresolved_alerts)} detail="Requires attention" tone="rose" />
      </div>

      <div className="monitoring-overview-grid">
        <section className="panel monitoring-status-panel">
          <PanelTitle
            eyebrow="Collection status"
            title="Request distribution"
            detail={`${formatNumber(summary.total_requests)} total collection requests`}
          />
          <StatusBreakdown label="COLLECTED" count={summary.collected} total={summary.total_requests} tone="collected" />
          <StatusBreakdown label="IN_PROGRESS" count={summary.in_progress} total={summary.total_requests} tone="in-progress" />
          <StatusBreakdown label="ASSIGNED" count={summary.assigned} total={summary.total_requests} tone="assigned" />
          <div className="monitoring-efficiency">
            <span>Collection efficiency</span>
            <strong>{formatNumber(summary.collection_efficiency, 1)}%</strong>
            <small>Collected requests ÷ total requests</small>
          </div>
        </section>

        <section className="panel monitoring-alert-panel">
          <PanelTitle eyebrow="Priority queue" title="Latest alerts" detail="Unresolved and high-severity alerts appear first" />
          <AlertList alerts={data.alerts} />
        </section>
      </div>

      <section className="panel monitoring-vehicle-panel">
        <PanelTitle eyebrow="Fleet status" title="Live / recent vehicle monitoring" detail="Latest recorded GPS position and current assigned work" />
        <VehicleTable vehicles={data.vehicles} />
      </section>

      <MonitoringMapPanel locations={mapLocations} />
      <section className="panel monitoring-pending-panel">
        <PanelTitle
          eyebrow="Work queue"
          title="Pending collections"
          detail={`${formatNumber(data.pending_requests.length)} assigned or in-progress requests · oldest first`}
        />
        <PendingTable requests={data.pending_requests} />
      </section>
      <section className="panel monitoring-ward-panel">
        <PanelTitle eyebrow="Ward health" title="Wards requiring attention" detail="Relative high/low thresholds are derived from current ward-level data" />
        <WardAttention wards={data.wards} />
      </section>

    </div>
  );
}
