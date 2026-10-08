"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import anime from "animejs";
import { api, errorMessage, post } from "../_lib/client";
import { useToast } from "../_lib/toast";
import { useConfirm } from "../_lib/confirm";

type MfaState = { enrolled: boolean; mandatory: boolean; recovery_codes_remaining: number };
type SessionRow = { id: string; user_agent: string | null; ip_address: string | null; created_at: string; last_seen_at: string; current: boolean };
type Overview = { mfa: MfaState; sessions: SessionRow[]; google_sign_in: boolean };

function ago(iso: string): string {
  const seconds = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

function parseAgent(ua: string | null): { browser: string; os: string } {
  if (!ua) return { browser: "Unknown browser", os: "" };
  let browser = "Browser";
  if (ua.includes("Firefox")) browser = "Firefox";
  else if (ua.includes("Edg/")) browser = "Edge";
  else if (ua.includes("Chrome")) browser = "Chrome";
  else if (ua.includes("Safari")) browser = "Safari";
  let os = "";
  if (ua.includes("Windows")) os = "Windows";
  else if (ua.includes("Mac OS")) os = "macOS";
  else if (ua.includes("Linux")) os = "Linux";
  else if (ua.includes("Android")) os = "Android";
  else if (ua.includes("iPhone") || ua.includes("iPad")) os = "iOS";
  return { browser, os };
}

export default function SecurityPage() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [codes, setCodes] = useState<string[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();
  const confirm = useConfirm();

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api<Overview>("/api/v1/auth/security");
      setOverview(data && typeof data === "object" && "mfa" in data ? data : null);
    } catch (reason) {
      setError(errorMessage(reason, "Security settings could not be loaded."));
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const run = async (action: () => Promise<unknown>, success: string) => {
    setBusy(true);
    setError(null);
    try {
      await action();
      toast.success(success);
      await load();
    } catch (reason) {
      toast.error(errorMessage(reason, "That change could not be completed."));
    } finally {
      setBusy(false);
    }
  };

  const codeFrom = (event: FormEvent<HTMLFormElement>) =>
    String(new FormData(event.currentTarget).get("code") ?? "").trim();

  function regenerate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const code = codeFrom(event);
    void run(async () => {
      const result = await post<{ recovery_codes: string[] }>("/api/v1/auth/mfa/recovery-codes/regenerate", { code });
      setCodes(result.recovery_codes);
    }, "New recovery codes generated. Old codes no longer work.");
  }

  async function disable(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const code = codeFrom(event);
    const ok = await confirm({ title: "Turn off two-step verification", message: "Your account will no longer require a second factor at sign-in. Are you sure?", confirmLabel: "Turn off", danger: true });
    if (!ok) return;
    void run(() => post("/api/v1/auth/mfa/disable", { code }), "Two-step verification turned off.");
  }

  async function revokeSession(sessionId: string) {
    const ok = await confirm({ message: "Sign out this device? They will need to log in again.", danger: true });
    if (!ok) return;
    void run(() => post("/api/v1/auth/sessions/revoke", { session_id: sessionId }), "Device signed out.");
  }

  async function revokeOthers() {
    const ok = await confirm({ title: "Sign out other devices", message: "All other sessions will be terminated immediately.", confirmLabel: "Sign out all", danger: true });
    if (!ok) return;
    void run(() => post("/api/v1/auth/sessions/revoke-others"), "Other devices were signed out.");
  }

  const mfa = overview?.mfa;
  const sessions = overview?.sessions ?? [];
  const otherCount = sessions.filter((s) => !s.current).length;

  const secRef = useRef<HTMLElement>(null);
  useEffect(() => {
    if (loading || !secRef.current) return;
    anime({ targets: secRef.current.querySelectorAll(".surface-card, .inventory-summary > div"), opacity: [0, 1], translateY: [22, 0], duration: 500, delay: anime.stagger(55, { start: 120 }), easing: "easeOutCubic" });
  }, [loading]);

  return <main className="workspace-page security-page" ref={secRef}>
    <div className="workspace-page-header">
      <div>
        <p className="eyebrow">ACCOUNT · SAFE BY DEFAULT</p>
        <h1>Keep your account <em>yours.</em></h1>
        <p className="workspace-page-intro">Two-step verification, recovery codes, and the devices signed in to your account.</p>
      </div>
      <div className="header-actions">
        <button className="button button-secondary" onClick={() => void load()} disabled={loading}>Refresh <span>↻</span></button>
      </div>
    </div>

    {error && <div className="workspace-alert" role="alert"><strong>{error}</strong><button className="ghost-button" onClick={() => void load()}>Try again <span>→</span></button></div>}
    {loading && !overview && <div className="dashboard-empty" role="status"><strong>Loading security settings</strong><span>Checking your account state…</span></div>}

    {overview && <>
      {/* MFA status hero */}
      <div className="report-hero-grid" style={{ marginBottom: 24 }}>
        <div className={`report-hero-card ${mfa?.enrolled ? "report-hero-dark" : "report-hero-warm"}`}>
          <span className="eyebrow">TWO-STEP VERIFICATION</span>
          <strong>{mfa?.enrolled ? "Enabled" : "Off"}</strong>
          <p>{mfa?.mandatory ? "Required for your role" : mfa?.enrolled ? "Your account has a second factor" : "Consider enabling for stronger protection"}</p>
        </div>
        <div className="report-hero-card">
          <span className="eyebrow">RECOVERY CODES</span>
          <strong>{mfa?.recovery_codes_remaining ?? 0}</strong>
          <p>codes remaining</p>
        </div>
        <div className="report-hero-card">
          <span className="eyebrow">ACTIVE SESSIONS</span>
          <strong>{sessions.length}</strong>
          <p>{otherCount} other {otherCount === 1 ? "device" : "devices"}</p>
        </div>
      </div>

      {/* MFA management */}
      <section className="surface-card" style={{ marginBottom: 16 }}>
        <div className="surface-card-heading">
          <div><p className="eyebrow">AUTHENTICATOR</p><h2>Two-step verification</h2></div>
          <span className={`pipeline-status ${mfa?.enrolled ? "status-paid" : "status-lost"}`}>{mfa?.enrolled ? "ACTIVE" : "INACTIVE"}</span>
        </div>

        {mfa?.enrolled ? <>
          <form className="manage-form" onSubmit={regenerate} style={{ padding: "16px 20px" }}>
            <p style={{ fontSize: "0.85rem", marginBottom: 12, opacity: 0.7 }}>Enter your authenticator code to generate fresh recovery codes. Existing codes will stop working.</p>
            <div className="form-grid">
              <label>Authenticator code<input name="code" inputMode="numeric" autoComplete="one-time-code" minLength={6} maxLength={16} required placeholder="6-digit code" /></label>
            </div>
            <div className="form-actions">
              <button className="button button-secondary" type="submit" disabled={busy}>{busy ? "Generating…" : "Generate new recovery codes"}</button>
            </div>
          </form>

          {codes && <div className="surface-card" style={{ margin: "0 20px 16px", padding: 16, background: "var(--surface-2, #f5f5f0)", borderRadius: 8 }}>
            <strong style={{ fontSize: "0.85rem" }}>Save these now — they are shown only once</strong>
            <pre style={{ marginTop: 8, padding: 12, background: "var(--surface-1, #fff)", borderRadius: 6, fontSize: "0.82rem", lineHeight: 1.7, overflowX: "auto" }}>{codes.join("\n")}</pre>
          </div>}

          {!mfa.mandatory && <form className="manage-form" onSubmit={(e) => void disable(e)} style={{ padding: "0 20px 16px" }}>
            <div className="form-grid">
              <label>Authenticator code<input name="code" inputMode="numeric" minLength={6} maxLength={16} required placeholder="Confirm with code" /></label>
            </div>
            <div className="form-actions">
              <button className="button button-danger" type="submit" disabled={busy}>{busy ? "Disabling…" : "Turn off two-step verification"}</button>
            </div>
          </form>}
        </> : <div style={{ padding: "16px 20px" }}>
          <p className="field-note">Sign out and sign back in to enroll an authenticator app. Your clinic admin can also make MFA mandatory for your role.</p>
        </div>}
      </section>

      {/* Active sessions */}
      <section className="surface-card">
        <div className="surface-card-heading">
          <div><p className="eyebrow">SIGNED-IN DEVICES</p><h2>Where you are signed in</h2></div>
          {otherCount > 0 && <button className="button button-secondary" disabled={busy} onClick={() => void revokeOthers()}>Sign out other devices</button>}
        </div>
        <div className="invoice-list">
          {sessions.map((item) => {
            const { browser, os } = parseAgent(item.user_agent);
            return <article className="invoice-row" key={item.id}>
              <div className="invoice-mark" style={{ fontSize: "1.2rem" }}>{item.current ? "●" : "○"}</div>
              <div className="invoice-main">
                <h3>{item.current ? "This device" : browser}{os ? ` · ${os}` : ""}</h3>
                <p style={{ fontSize: "0.8rem", opacity: 0.65 }}>{item.user_agent ?? "Unknown browser"}</p>
                <small>Last active {ago(item.last_seen_at)} · Signed in {new Date(item.created_at).toLocaleDateString()}</small>
              </div>
              <div className="invoice-actions">
                {item.current
                  ? <span className="pipeline-status status-paid">CURRENT</span>
                  : <button className="text-control" disabled={busy} onClick={() => void revokeSession(item.id)}>Sign out</button>}
              </div>
            </article>;
          })}
        </div>

        {overview.google_sign_in && <p className="field-note" style={{ padding: "12px 20px" }}>Google sign-in is available for accounts whose email matches an invited user.</p>}
      </section>
    </>}
  </main>;
}
