"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import DemoDashboard from "@/components/DemoDashboard";
import MonitoringDashboard from "@/components/MonitoringDashboard";
import { api, clearToken } from "@/lib/api";
import { isDemoUser } from "@/lib/demoAccounts";
import type { User } from "@/lib/types";
import "../dashboard.css";

export default function AdminPage() {
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
        if (authenticatedUser.role !== "ADMIN") {
          router.replace(authenticatedUser.role === "MONITOR" ? "/monitoring" : "/");
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

  function signOut() {
    clearToken();
    router.replace("/monitor-login");
  }

  if (!user) {
    return <div className="center-state"><div className="spinner" />Verifying admin access...</div>;
  }
  if (isDemoUser(user)) {
    return <DemoDashboard user={user} onSignOut={signOut} />;
  }

  return (
    <main className="monitoring-route-shell">
      <header className="monitoring-route-header">
        <div>
          <p className="breadcrumb">ADMIN / CONTROL ROOM</p>
          <h1>Admin Dashboard</h1>
          <p className="muted">Signed in as {user.name}</p>
        </div>
        <button className="outline-button" onClick={signOut}>Sign out</button>
      </header>
      <MonitoringDashboard />
    </main>
  );
}
