import type {
  Alert,
  AlertAnalytics,
  AnalyticsOverview,
  AreaAnalytics,
  AreaSegregation,
  CollectionRequest,
  Complaint,
  ComplaintAnalytics,
  DailyWaste,
  MonitoringDashboardData,
  Penalty,
  RewardTotal,
  Team,
  TeamOptions,
  User,
  Vehicle,
  VehicleLocation,
  WasteReport,
  WasteTypeAnalytics,
  WorkerPerformance,
} from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

function token(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem("smart-waste-token");
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  const authToken = token();
  if (authToken) headers.set("Authorization", `Bearer ${authToken}`);

  const response = await fetch(`${API_URL}${path}`, { ...options, headers });
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null;
    throw new ApiError(body?.detail ?? `Request failed (${response.status})`, response.status);
  }
  return response.json() as Promise<T>;
}

export const api = {
  register: (payload: {
    name: string;
    email: string;
    phone_number: string;
    password: string;
    role: "CITIZEN" | "WORKER";
  }) => request<User>("/register", {
    method: "POST",
    body: JSON.stringify(payload),
  }),
  login: (identifier: string, password: string) => request<{ access_token: string; token_type: string }>("/login", {
    method: "POST",
    body: JSON.stringify({
      ...(identifier.match(/^w:\d+$/i)
        ? { worker_id: Number(identifier.slice(2)) }
        : identifier.match(/^u:\d+$/i)
          ? { user_id: Number(identifier.slice(2)) }
          : /^\d+$/.test(identifier)
            ? { user_id: Number(identifier) }
            : { email: identifier }),
      password,
    }),
  }),
  me: () => request<User>("/users/me"),
  myReports: () => request<WasteReport[]>("/waste-reports/my"),
  createReport: (payload: Omit<WasteReport, "report_id" | "citizen_id" | "status">) => request<WasteReport>("/waste-reports", {
    method: "POST", body: JSON.stringify(payload),
  }),
  myComplaints: () => request<Complaint[]>("/complaints/my"),
  createComplaint: (payload: { area_id: number; category: string; description: string; priority: string }) => request<Complaint>("/complaints", {
    method: "POST", body: JSON.stringify(payload),
  }),
  rewardTotal: () => request<RewardTotal>("/rewards/my/total"),
  penalties: () => request<Penalty[]>("/penalties/my"),
  myCollections: () => request<CollectionRequest[]>("/collection-requests/my"),
  collect: (requestId: number) => request<CollectionRequest>(`/collection-requests/${requestId}/collect`, { method: "PUT" }),
  rate: (requestId: number, rating: number) => request(`/collection-requests/${requestId}/rating`, {
    method: "POST", body: JSON.stringify({ rating }),
  }),
  vehicles: () => request<Vehicle[]>("/vehicles"),
  recordLocation: (vehicleId: number, latitude: number, longitude: number) => request<VehicleLocation>(`/vehicles/${vehicleId}/locations`, {
    method: "POST", body: JSON.stringify({ latitude, longitude }),
  }),
  overview: () => request<AnalyticsOverview>("/monitor/analytics/overview"),
  areaAnalytics: () => request<AreaAnalytics[]>("/monitor/analytics/waste-by-area"),
  segregationByArea: () => request<AreaSegregation[]>("/monitor/analytics/segregation-by-area"),
  teams: () => request<Team[]>("/monitor/teams"),
  teamOptions: () => request<TeamOptions>("/monitor/teams/options"),
  createTeam: (payload: {
    team_name: string;
    area_id: number;
    leader_worker_id: number;
    worker_ids: number[];
    vehicle_id: number | null;
  }) => request<Team>("/monitor/teams", {
    method: "POST",
    body: JSON.stringify(payload),
  }),
  typeAnalytics: () => request<WasteTypeAnalytics[]>("/monitor/analytics/waste-by-type"),
  workerPerformance: () => request<WorkerPerformance[]>("/monitor/analytics/worker-performance"),
  complaintAnalytics: () => request<ComplaintAnalytics>("/monitor/analytics/complaints"),
  alertAnalytics: () => request<AlertAnalytics>("/monitor/analytics/alerts"),
  dailyWaste: () => request<DailyWaste[]>("/monitor/analytics/daily-waste"),
  alerts: () => request<Alert[]>("/monitor/alerts/open"),
  monitoring: () => request<MonitoringDashboardData>("/monitor/monitoring"),
};

export function saveToken(value: string) {
  window.localStorage.setItem("smart-waste-token", value);
}

export function clearToken() {
  window.localStorage.removeItem("smart-waste-token");
}
