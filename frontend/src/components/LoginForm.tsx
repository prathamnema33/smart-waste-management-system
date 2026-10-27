"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { api, clearToken, saveToken } from "@/lib/api";
import { demoAccounts } from "@/lib/demoAccounts";
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
  const [copied, setCopied] = useState("");
  const isOperationsLogin = mode === "operations";

  async function authenticate(loginIdentifier: string, loginPassword: string) {
    setBusy(true);
    setError("");
    try {
      const session = await api.login(loginIdentifier.trim(), loginPassword);
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

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await authenticate(identifier, password);
  }

  async function loginAsDemo(demo: (typeof demoAccounts)[number]) {
    setIdentifier(demo.identifier);
    setPassword(demo.password);
    await authenticate(demo.identifier, demo.password);
  }

  async function copyCredentials(demo: (typeof demoAccounts)[number]) {
    try {
      await navigator.clipboard.writeText(
        `User ID: ${demo.identifier}\nPassword: ${demo.password}`,
      );
      setCopied(demo.identifier);
    } catch {
      setError("Could not copy credentials. Please copy them from the card.");
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
        <div className="login-content">
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
        {!isOperationsLogin && (
          <section className="demo-access" aria-labelledby="demo-access-title">
            <div className="demo-access-heading">
              <div>
                <p className="eyebrow">PUBLIC DEMONSTRATION ACCOUNTS</p>
                <h2 id="demo-access-title">Explore Demo Accounts</h2>
                <p className="muted">Public credentials · Read-only access · Synthetic sample data</p>
              </div>
            </div>
            <div className="demo-account-grid">
              {demoAccounts.map((demo) => (
                <article className="demo-account-card" key={demo.identifier}>
                  <h3>{demo.label}</h3>
                  <p><span>User ID</span><code>{demo.identifier}</code></p>
                  <p><span>Password</span><code>{demo.password}</code></p>
                  <div className="demo-account-actions">
                    <button
                      className="primary-button compact"
                      disabled={busy}
                      onClick={() => void loginAsDemo(demo)}
                      type="button"
                    >
                      {busy ? "Signing in..." : "Login as Demo"}
                    </button>
                    <button
                      className="small-button"
                      onClick={() => void copyCredentials(demo)}
                      type="button"
                    >
                      {copied === demo.identifier ? "Copied" : "Copy credentials"}
                    </button>
                  </div>
                </article>
              ))}
            </div>
          </section>
        )}
        </div>
      </section>
    </main>
  );
}
