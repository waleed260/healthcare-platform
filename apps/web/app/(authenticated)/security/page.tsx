"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, errorMessage, post } from "../_lib/client";

type Overview = { mfa: { enrolled: boolean; mandatory: boolean; recovery_codes_remaining: number }; sessions: { id: string; user_agent: string | null; created_at: string; last_seen_at: string; current: boolean }[]; google_sign_in: boolean };

export default function SecurityPage() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [codes, setCodes] = useState<string[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await api<Overview>("/api/v1/auth/security");
      setOverview(data && typeof data === "object" && "mfa" in data ? data : null);
    } catch (reason) { setError(errorMessage(reason, "Security settings could not be loaded.")); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const run = async (action: () => Promise<unknown>, success: string) => {
    setBusy(true); setError(null); setNotice(null);
    try { await action(); setNotice(success); await load(); } catch (reason) { setError(errorMessage(reason, "That change could not be completed.")); } finally { setBusy(false); }
  };
  const codeFrom = (event: FormEvent<HTMLFormElement>) => String(new FormData(event.currentTarget).get("code") ?? "").trim();
  const regenerate = (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const code = codeFrom(event); void run(async () => { const result = await post<{ recovery_codes: string[] }>("/api/v1/auth/mfa/recovery-codes/regenerate", { code }); setCodes(result.recovery_codes); }, "New recovery codes generated. Old codes no longer work."); };
  const disable = (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const code = codeFrom(event); if (window.confirm("Turn off two-step verification for your account?")) void run(() => post("/api/v1/auth/mfa/disable", { code }), "Two-step verification turned off."); };

  return <main className="workspace-page security-page">
    <div className="workspace-page-header"><div><p className="eyebrow">ACCOUNT · SAFE BY DEFAULT</p><h1>Keep your account <em>yours.</em></h1><p className="workspace-page-intro">Two-step verification, recovery codes and the devices signed in to your account.</p></div></div>
    {error && <div className="workspace-alert" role="alert"><strong>{error}</strong></div>}
    {notice && <div className="permission-strip" aria-live="polite"><span className="permission-ok">{notice}</span></div>}
    {overview && <>
      <section className="surface-card"><div className="surface-card-heading"><div><p className="eyebrow">TWO-STEP VERIFICATION</p><h2>{overview.mfa.enrolled ? "On" : "Off"}{overview.mfa.mandatory ? " · required for your role" : ""}</h2></div><span className="muted-mono">{overview.mfa.recovery_codes_remaining} RECOVERY CODES LEFT</span></div>
        {overview.mfa.enrolled ? <><form className="manage-form" onSubmit={regenerate}><div className="form-grid"><label>Authenticator code<input name="code" inputMode="numeric" autoComplete="one-time-code" minLength={6} maxLength={16} required /></label></div><div className="form-actions"><button className="button button-secondary" type="submit" disabled={busy}>Generate new recovery codes</button></div></form>
          {codes && <div className="auth-help"><strong>Save these now — they are shown once</strong><code>{codes.join("\n")}</code></div>}
          {!overview.mfa.mandatory && <form className="manage-form" onSubmit={disable}><div className="form-grid"><label>Authenticator code<input name="code" inputMode="numeric" minLength={6} maxLength={16} required /></label></div><div className="form-actions"><button className="button button-danger" type="submit" disabled={busy}>Turn off two-step verification</button></div></form>}</>
          : <p className="field-note">Sign out and back in to enroll an authenticator app.</p>}
      </section>
      <section className="surface-card"><div className="surface-card-heading"><div><p className="eyebrow">SIGNED-IN DEVICES</p><h2>Where you’re signed in.</h2></div><button className="button button-secondary" disabled={busy || overview.sessions.length < 2} onClick={() => void run(() => post("/api/v1/auth/sessions/revoke-others"), "Other devices were signed out.")}>Sign out other devices</button></div>
        <div className="invoice-list">{overview.sessions.map((item) => <article className="invoice-row" key={item.id}><div className="invoice-mark">{item.current ? "●" : "○"}</div><div className="invoice-main"><h3>{item.current ? "This device" : "Another device"}</h3><p>{item.user_agent ?? "Unknown browser"}</p><small>Last active {new Date(item.last_seen_at).toLocaleString()}</small></div>{!item.current && <div className="invoice-actions"><button className="text-control" disabled={busy} onClick={() => void run(() => post("/api/v1/auth/sessions/revoke", { session_id: item.id }), "Device signed out.")}>Sign out</button></div>}</article>)}</div>
        {overview.google_sign_in && <p className="field-note">Google sign-in is available for accounts whose email matches an invited user.</p>}
      </section></>}
  </main>;
}
