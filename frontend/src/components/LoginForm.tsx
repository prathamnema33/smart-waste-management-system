"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { api, clearToken, saveToken } from "@/lib/api";
import type { User } from "@/lib/types";
import "./auth.css";

export default function LoginForm({
  mode,
  onLogin,
}: {
  mode: "workspace" | "operations";
  onLogin: (user: User) => void;
}) {
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const isOperationsLogin = mode === "operations";

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const session = await api.login(identifier.trim(), password);
      saveToken(session.access_token);
      const user = await api.me();
      if (isOperationsLogin && user.role !== "ADMIN" && user.role !== "MONITOR") {
        clearToken();
        setError("This account does not have Admin or Monitor access.");
        return;
      }
      onLogin(user);
    } catch (loginError) {
      clearToken();
      setError(loginError instanceof Error ? loginError.message : "Unable to sign in.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login-page">
      <section className="login-art">
        <div className="brand-mark">SW</div>
        <p className="eyebrow">Civic operations platform</p>
        <h1>Cleaner streets.<br /><em>Smarter cycles.</em></h1>
        <p className="art-copy">
          One operational view for the people, vehicles, and decisions behind a better waste collection system.
        </p>
        <div className="signal-row"><span /><span /><span /><b>LIVE OPERATIONS</b></div>
      </section>
      <section className="login-panel">
        <div className="login-card">
          <p className="eyebrow">{isOperationsLogin ? "CONTROL ROOM ACCESS" : "SMART WASTE MANAGEMENT"}</p>
          <h2>{isOperationsLogin ? "Admin & Monitor sign in" : "Welcome back"}</h2>
          <p className="muted">
            {isOperationsLogin
              ? "Sign in with an authorized operations account."
              : "Sign in to your citizen or worker workspace."}
          </p>
          <form onSubmit={submit}>
            <label>
              Email / User ID
              <input
                type="text"
                value={identifier}
                onChange={(event) => setIdentifier(event.target.value)}
                placeholder="Email, User ID, or Worker ID (W:123)"
                autoComplete="username"
                required
              />
            </label>
            <label>
              Password
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="Enter your password"
                autoComplete="current-password"
                required
              />
            </label>
            {error && <div className="error-box" role="alert">{error}</div>}
            <button className="primary-button" disabled={busy}>
              {busy ? "Signing in..." : "Enter workspace"}<span>→</span>
            </button>
          </form>
          <p className="security-note">Access is protected by the FastAPI JWT gateway.</p>
          <p className="login-switch">
            {isOperationsLogin ? (
              <>Citizen or Worker? <Link href="/">Open workspace sign in</Link></>
            ) : (
              <>Admin or Monitor? <Link href="/monitor-login">Open control room sign in</Link></>
            )}
          </p>
          {!isOperationsLogin && (
            <p className="login-switch">
              Don&apos;t have an account? <Link href="/signup">Sign Up</Link>
            </p>
          )}
        </div>
      </section>
    </main>
  );
}
