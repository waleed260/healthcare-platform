"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";

async function extractError(response: Response): Promise<string> {
  const payload = await response.json().catch(() => null) as { error?: { message?: string } } | null;
  return payload?.error?.message ?? "This invitation link is invalid or expired.";
}

export default function StaffSetupPage() {
  const [token, setToken] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [complete, setComplete] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setToken(new URLSearchParams(window.location.search).get("token") ?? "");
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    if (!token) { setError("This invitation link is missing its one-time token."); return; }
    if (password.length < 12) { setError("Password must be at least 12 characters."); return; }
    if (password !== confirmation) { setError("The passwords do not match."); return; }
    if (!displayName.trim()) { setError("Please enter your name."); return; }
    setBusy(true);
    try {
      const response = await fetch("/api/v1/auth/manual-invite/consume", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, password, display_name: displayName.trim() }),
      });
      if (!response.ok) throw new Error(await extractError(response));
      setComplete(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to complete the invitation setup.");
    } finally { setBusy(false); }
  }

  return <main className="auth-page"><div className="auth-panel">
    <Link className="wordmark" href="/">care<span>/</span>fully</Link>
    <div className="auth-copy">
      <p className="eyebrow">STAFF INVITATION</p>
      <h1>{complete ? <>Welcome<br /><em>aboard.</em></> : <>Set up your<br /><em>account.</em></>}</h1>
      <p>{complete ? "Your account is ready. Sign in with the email your clinic used to invite you." : "Your clinic administrator invited you. Choose a display name and password to get started."}</p>
    </div>
    {error && <div className="workspace-alert" role="alert">{error}</div>}
    {!token && !complete && <div className="workspace-alert" role="alert">No invitation token found. Please use the link from your invitation email.</div>}
    {complete
      ? <Link className="button button-primary auth-submit" href="/login">Sign in <span>→</span></Link>
      : <form className="auth-form" onSubmit={submit}>
        <label htmlFor="display-name">Your name</label>
        <input id="display-name" type="text" autoComplete="name" required minLength={1} maxLength={160} value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder="Dr. Samira Khan" />
        <label htmlFor="new-password">Password</label>
        <input id="new-password" type="password" autoComplete="new-password" minLength={12} required value={password} onChange={(e) => setPassword(e.target.value)} />
        <label htmlFor="confirm-password">Confirm password</label>
        <input id="confirm-password" type="password" autoComplete="new-password" minLength={12} required value={confirmation} onChange={(e) => setConfirmation(e.target.value)} />
        <button className="button button-primary auth-submit" type="submit" disabled={busy || !token}>{busy ? "Setting up…" : "Create account"}<span>→</span></button>
        <p className="auth-help">Use at least 12 characters with upper- and lowercase letters and a number. This link expires after 24 hours and can only be used once.</p>
      </form>}
    <p className="auth-footer"><Link href="/login">Return to sign in</Link></p>
  </div></main>;
}
