"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import "@/components/auth.css";
import "./signup.css";
import "../dashboard.css";

export default function SignupPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phoneNumber, setPhoneNumber] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [role, setRole] = useState<"CITIZEN" | "WORKER">("CITIZEN");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    if (!success) return;
    const timeout = window.setTimeout(() => router.replace("/"), 1800);
    return () => window.clearTimeout(timeout);
  }, [router, success]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    if (password !== confirmPassword) {
      setError("Password and Confirm Password must match.");
      return;
    }
    const phoneDigits = phoneNumber.replace(/\D/g, "");
    if (!/^\+?[0-9][0-9\s().-]*$/.test(phoneNumber.trim()) || phoneDigits.length < 7 || phoneDigits.length > 15) {
      setError("Enter a valid phone number with 7 to 15 digits.");
      return;
    }
    if (new TextEncoder().encode(password).length > 72) {
      setError("Password must be no more than 72 UTF-8 bytes.");
      return;
    }
    setBusy(true);
    try {
      await api.register({
        name: name.trim(),
        email: email.trim(),
        phone_number: phoneNumber.trim(),
        password,
        role,
      });
      setSuccess(true);
    } catch (signupError) {
      setError(signupError instanceof Error ? signupError.message : "Unable to create your account.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login-page signup-page">
      <section className="login-art">
        <div className="brand-mark">SW</div>
        <p className="eyebrow">Civic operations platform</p>
        <h1>Cleaner streets.<br /><em>Smarter cycles.</em></h1>
        <p className="art-copy">
          Create an account to report waste and follow collection activity in your neighborhood.
        </p>
        <div className="signal-row"><span /><span /><span /><b>COMMUNITY ACCESS</b></div>
      </section>
      <section className="login-panel">
        <div className="login-card">
          <p className="eyebrow">SMART WASTE MANAGEMENT</p>
          <h2>Create your account</h2>
          <p className="muted">Sign up for a citizen workspace.</p>
          {success ? (
            <div className="signup-success">
              <div className="success-box" role="status">
                Registration successful. Redirecting you to sign in...
              </div>
              <Link className="signup-login-link" href="/">Sign in now</Link>
            </div>
          ) : (
            <form className="signup-form" onSubmit={submit}>
              <label>
                Full Name
                <input
                  type="text"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  autoComplete="name"
                  minLength={1}
                  maxLength={100}
                  required
                />
              </label>
              <label>
                Email
                <input
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  autoComplete="email"
                  maxLength={150}
                  required
                />
              </label>
              <label>
                Phone Number
                <input
                  type="tel"
                  value={phoneNumber}
                  onChange={(event) => setPhoneNumber(event.target.value)}
                  autoComplete="tel"
                  maxLength={32}
                  title="Enter a phone number using digits and optional spaces, +, parentheses, periods, or hyphens."
                  required
                />
              </label>
              <label>
                Password
                <input
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  autoComplete="new-password"
                  minLength={8}
                  maxLength={72}
                  required
                />
              </label>
              <label>
                Confirm Password
                <input
                  type="password"
                  value={confirmPassword}
                  onChange={(event) => setConfirmPassword(event.target.value)}
                  autoComplete="new-password"
                  minLength={8}
                  maxLength={72}
                  required
                />
              </label>
              <label>
                Role
                <select
                  value={role}
                  onChange={(event) => setRole(event.target.value === "WORKER" ? "WORKER" : "CITIZEN")}
                  aria-describedby="worker-role-note"
                  required
                >
                  <option value="CITIZEN">Citizen</option>
                  <option value="WORKER">Worker</option>
                </select>
                <small id="worker-role-note" className="field-hint">
                  {role === "WORKER"
                    ? "Worker accounts need an assigned area and must be created by an administrator."
                    : "Worker accounts are provisioned by an administrator."}
                </small>
              </label>
              {error && <div className="error-box" role="alert">{error}</div>}
              <button className="primary-button" disabled={busy || role === "WORKER"}>
                {busy ? "Creating account..." : role === "WORKER" ? "Worker account required" : "Create account"}<span>→</span>
              </button>
            </form>
          )}
          <p className="login-switch">
            Already have an account? <Link href="/">Sign in</Link>
          </p>
        </div>
      </section>
    </main>
  );
}
