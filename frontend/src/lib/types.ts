export type Role = "CITIZEN" | "WORKER" | "MONITOR" | "ADMIN";

export interface User {
  user_id: number;
  name: string;
  email: string;
  role: Role;
}

export interface WasteReport {
  report_id: number;
  citizen_id: number;
  area_id: number;
  waste_type: string;
  quantity_kg: number;
  latitude: number;
  longitude: number;
  priority: string;
  status: string;
}

export interface CollectionRequest {
  request_id: number;
  report_id: number;
  worker_id: number;
  assigned_at: string | null;
  collected_at: string | null;
  status: string;
}

export interface Complaint {
  complaint_id: number;
  citizen_id: number;
  area_id: number;
  category: string;
  description: string;
  priority: string | null;
  status: string | null;
  created_at: string | null;
  resolved_at: string | null;
}

export interface RewardTotal {
  citizen_id: number;
  total_points: number;
}

export interface Penalty {
  penalty_id: number;
  citizen_id: number;
  reason: string;
  amount: number;
  status: string;
  created_at: string;
}

export interface Vehicle {
  vehicle_id: number;
  vehicle_number: string;
  worker_id: number;
  status: string | null;
}

export interface VehicleLocation {
  location_id: number;
  vehicle_id: number;
  latitude: number;
  longitude: number;
  recorded_at: string | null;
}

export interface Alert {
  alert_id: number;
  area_id: number;
  alert_type: string;
  severity: string | null;
  message: string;
  created_at: string | null;
  status: string | null;
}

export interface MonitoringStatusCounts {
  total_requests: number;
  assigned: number;
  in_progress: number;
  collected: number;
  active_requests: number;
  unresolved_alerts: number;
  collection_efficiency: number;
}

export interface MonitoringVehicle {
  vehicle_id: number;
  vehicle_number: string;
  vehicle_status: string | null;
  collection_status: string | null;
  worker_id: number;
  worker_name: string | null;
  team_name: string | null;
  area_name: string | null;
  ward_name: string | null;
  ward_number: string | null;
  latitude: number | null;
  longitude: number | null;
  last_gps_update: string | null;
}

export interface MonitoringPendingRequest {
  request_id: number;
  report_id: number;
  ward_name: string | null;
  ward_number: string | null;
  area_name: string | null;
  worker_name: string | null;
  vehicle_number: string | null;
  status: string;
  requested_at: string | null;
}

export interface MonitoringAlert {
  alert_id: number;
  alert_type: string;
  severity: string | null;
  ward_name: string | null;
  ward_number: string | null;
  area_name: string | null;
  message: string;
  created_at: string | null;
  status: string | null;
}

export interface MonitoringWard {
  ward_id: number;
  ward_name: string;
  ward_number: string;
  total_waste_kg: number;
  total_reports: number;
  total_requests: number;
  pending_collections: number;
  collected_collections: number;
  collection_efficiency: number;
  total_complaints: number;
  open_complaints: number;
  unresolved_alerts: number;
  attention_level: "HIGH" | "WATCH" | "NORMAL";
  attention_reasons: string[];
}

export interface MonitoringMapMarker {
  id: number;
  latitude: number;
  longitude: number;
  label: string;
  status: string | null;
  detail: string;
  created_at: string | null;
}

export interface MonitoringDashboardData {
  updated_at: string;
  summary: MonitoringStatusCounts;
  vehicles: MonitoringVehicle[];
  pending_requests: MonitoringPendingRequest[];
  alerts: MonitoringAlert[];
  wards: MonitoringWard[];
  map_locations: {
    vehicles: MonitoringMapMarker[];
    waste_reports: MonitoringMapMarker[];
    collections: MonitoringMapMarker[];
    alerts: MonitoringMapMarker[];
  };
}

export interface AnalyticsOverview {
  total_waste_reports: number;
  total_waste_kg: number;
  total_collections: number;
  pending_collections: number;
  collection_efficiency: number;
  total_complaints: number;
  open_complaints: number;
  total_rewards_points: number;
  total_penalty_amount: number;
  open_alerts: number;
}

export interface AreaAnalytics {
  area_id: number;
  area_name: string;
  total_reports: number;
  total_waste_kg: number;
  avg_waste_per_report: number;
  total_collections: number;
  pending_collections: number;
  total_complaints: number;
  open_complaints: number;
}

export interface AreaSegregation {
  area_id: number;
  area_name: string;
  latitude: number | null;
  longitude: number | null;
  total_ratings: number;
  average_rating: number;
  excellent_ratings: number;
  good_ratings: number;
  average_ratings: number;
  poor_ratings: number;
  segregation_score: number;
}

export interface Team {
  team_id: number;
  team_name: string;
  area_id: number;
  area_name: string;
  leader_worker_id: number;
  leader_name: string;
  worker_ids: number[];
  worker_names: string[];
  worker_count: number;
  vehicle_id: number | null;
  vehicle_number: string | null;
  min_latitude: number | null;
  max_latitude: number | null;
  min_longitude: number | null;
  max_longitude: number | null;
  zone_boundary: [number, number][] | null;
}

export interface TeamOptions {
  areas: { area_id: number; area_name: string; has_team: boolean }[];
  workers: {
    worker_id: number;
    worker_name: string;
    area_id: number;
    team_id: number | null;
  }[];
  vehicles: {
    vehicle_id: number;
    vehicle_number: string;
    status: string | null;
    worker_id: number;
    worker_name: string;
    area_id: number;
    team_ids: number[];
  }[];
}

export interface WasteTypeAnalytics {
  waste_type: string;
  report_count: number;
  total_waste_kg: number;
  average_waste_kg: number;
}

export interface WorkerPerformance {
  worker_id: number;
  worker_name: string;
  total_assigned: number;
  total_collected: number;
  total_pending: number;
  collection_efficiency: number;
}

export interface ComplaintAnalytics {
  total_complaints: number;
  open_complaints: number;
  in_progress_complaints: number;
  resolved_complaints: number;
  by_category: { category: string; total: number }[];
}

export interface AlertAnalytics {
  total_alerts: number;
  open_alerts: number;
  resolved_alerts: number;
  critical_alerts: number;
  high_alerts: number;
}

export interface DailyWaste {
  date: string;
  report_count: number;
  total_waste_kg: number;
  average_waste_kg: number;
}
