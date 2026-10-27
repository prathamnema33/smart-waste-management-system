"use client";

import type { Role, User } from "@/lib/types";

const dashboardContent: Record<
  Role,
  {
    title: string;
    description: string;
    metrics: { label: string; value: string; detail: string }[];
    activity: { label: string; detail: string; status: string }[];
  }
> = {
  ADMIN: {
    title: "Admin Dashboard",
    description: "A read-only overview using fictional demonstration data.",
    metrics: [
      { label: "Demo accounts", value: "4", detail: "Sample users only" },
      { label: "Waste reports", value: "128", detail: "Synthetic records" },
      { label: "Collections", value: "92%", detail: "Sample completion rate" },
      { label: "Open alerts", value: "3", detail: "Fictional alerts" },
    ],
    activity: [
      { label: "Sample Ward 01", detail: "32 reports · 94% collected", status: "On track" },
      { label: "Sample Ward 02", detail: "21 reports · 2 pending", status: "In progress" },
      { label: "Sample Ward 03", detail: "18 reports · 1 alert", status: "Review" },
    ],
  },
  MONITOR: {
    title: "Monitoring Dashboard",
    description: "Sample collection activity; no live or personal data is shown.",
    metrics: [
      { label: "Sample requests", value: "128", detail: "Fictional records" },
      { label: "Collected", value: "118", detail: "Sample status" },
      { label: "Collection rate", value: "92%", detail: "Demonstration metric" },
      { label: "Sample alerts", value: "3", detail: "Fictional alerts" },
    ],
    activity: [
      { label: "Sample Crew A", detail: "Ward 01 · 4 collections", status: "Active" },
      { label: "Sample Crew B", detail: "Ward 02 · 3 collections", status: "Active" },
      { label: "Sample Crew C", detail: "Ward 03 · 2 pending", status: "Review" },
    ],
  },
  WORKER: {
    title: "Worker Dashboard",
    description: "A fictional route preview. Demo accounts cannot update collections or GPS.",
    metrics: [
      { label: "Sample assignments", value: "5", detail: "Fictional route" },
      { label: "Completed", value: "3", detail: "Sample status" },
      { label: "Pending", value: "2", detail: "Sample status" },
      { label: "Route area", value: "Ward 01", detail: "Fictional area" },
    ],
    activity: [
      { label: "Sample stop 01", detail: "Ward 01 · Organic waste", status: "Collected" },
      { label: "Sample stop 02", detail: "Ward 01 · Recyclables", status: "Collected" },
      { label: "Sample stop 03", detail: "Ward 01 · Mixed waste", status: "Pending" },
    ],
  },
  CITIZEN: {
    title: "Citizen Dashboard",
    description: "A sample household view. No real citizen information is included.",
    metrics: [
      { label: "Sample reports", value: "3", detail: "Fictional records" },
      { label: "Collected", value: "2", detail: "Sample status" },
      { label: "Green points", value: "45", detail: "Sample balance" },
      { label: "Complaints", value: "1", detail: "Fictional record" },
    ],
    activity: [
      { label: "Sample report 01", detail: "Organic waste · Ward 01", status: "Collected" },
      { label: "Sample report 02", detail: "Recyclables · Ward 01", status: "Assigned" },
      { label: "Sample report 03", detail: "Paper · Ward 01", status: "Pending" },
    ],
  },
};

export default function DemoDashboard({
  user,
  onSignOut,
}: {
  user: User;
  onSignOut: () => void;
}) {
  const content = dashboardContent[user.role];

  return (
    <main className="demo-dashboard">
      <header className="demo-dashboard-header">
        <div className="brand">
          <div className="brand-mark small">SW</div>
          <div><strong>Smart Waste</strong><span>Public demo</span></div>
        </div>
        <button className="outline-button" onClick={onSignOut}>Sign out</button>
      </header>
      <section className="demo-dashboard-content">
        <div className="demo-banner">
          <strong>PUBLIC DEMONSTRATION ACCOUNT · READ ONLY</strong>
          <p>All dashboard values below are synthetic samples. Changes are disabled.</p>
        </div>
        <div className="demo-dashboard-title">
          <p className="breadcrumb">{user.role} / DEMONSTRATION</p>
          <h1>{content.title}</h1>
          <p className="muted">{content.description}</p>
        </div>
        <div className="metric-grid">
          {content.metrics.map((metric, index) => (
            <div className={`metric-card ${index === 1 ? "lime" : index === 2 ? "amber" : ""}`} key={metric.label}>
              <span className="metric-label">{metric.label}</span>
              <strong>{metric.value}</strong>
              <small>{metric.detail}</small>
            </div>
          ))}
        </div>
        <section className="panel demo-activity">
          <div className="section-title">
            <div><p className="eyebrow">Synthetic sample data</p><h2>Recent activity</h2></div>
            <span className="pill">Read only</span>
          </div>
          {content.activity.map((item) => (
            <div className="history-row" key={item.label}>
              <div><strong>{item.label}</strong><small>{item.detail}</small></div>
              <span className="status active">{item.status}</span>
            </div>
          ))}
        </section>
      </section>
    </main>
  );
}
