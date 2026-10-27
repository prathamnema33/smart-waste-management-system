"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import MonitoringDashboard from "@/components/MonitoringDashboard";
import { api, clearToken } from "@/lib/api";
import type { User } from "@/lib/types";
import "../dashboard.css";

export default function MonitoringPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    let active = true;
    async function restoreSession() {
      if (!localStorage.getItem("smart-waste-token")) {
        router.replace("/monitor-login");
        return;
      }
      try {
        const authenticatedUser = await api.me();
        if (authenticatedUser.role !== "ADMIN" && authenticatedUser.role !== "MONITOR") {
          router.replace("/");
          return;
        }
        if (active) setUser(authenticatedUser);
      } catch {
        clearToken();
        router.replace("/monitor-login");
      }
    }
    const timer = window.setTimeout(() => void restoreSession(), 0);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [router]);

  function logout() {
    clearToken();
    router.replace("/monitor-login");
  }

  if (!user) {
    return <div className="center-state"><div className="spinner" />Verifying operations access...</div>;
  }

  return (
    <main className="monitoring-route-shell">
      <header className="monitoring-route-header">
        <div>
          <p className="breadcrumb">{user.role} / CONTROL ROOM</p>
          <h1>Collection monitoring</h1>
          <p className="muted">Signed in as {user.name}</p>
        </div>
        <div className="monitoring-route-actions">
          <Link className="outline-button" href="/">Operational analytics & alerts</Link>
          <button className="outline-button" onClick={logout}>Sign out</button>
        </div>
      </header>
      <MonitoringDashboard />
    </main>
  );
}
