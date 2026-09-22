"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";

async function errorMessage(response: Response): Promise<string> {
  const payload = await response.json().catch(() => null) as { error?: { message?: string } } | null;
  return payload?.error?.message ?? "This reset link is invalid or expired.";
}

export default function ResetPasswordPage() {
  const [token, setToken] = useState("");
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
    if (!token) { setError("This reset link is missing its one-time token."); return; }
    if (password !== confirmation) { setError("The passwords do not match."); return; }
    setBusy(true);
    try {
      const response = await fetch("/api/v1/auth/manual-reset/consume", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, new_password: password }),
      });
      if (!response.ok) throw new Error(await errorMessage(response));
      setComplete(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to reset the password.");
    } finally { setBusy(false); }
  }

  return <main className="auth-page"><div className="auth-panel"><Link className="wordmark" href="/">care<span>/</span>fully</Link><div className="auth-copy"><p className="eyebrow">MANUAL ACCOUNT RECOVERY</p><h1>{complete ? <>You&apos;re<br /><em>ready.</em></> : <>Choose a<br /><em>password.</em></>}</h1><p>{complete ? "Your password was updated and all previous sessions were signed out." : "Use the one-time link supplied by your clinic administrator."}</p></div>{error && <div className="workspace-alert" role="alert">{error}</div>}{complete ? <Link className="button button-primary auth-submit" href="/login">Return to sign in <span>→</span></Link> : <form className="auth-form" onSubmit={submit}><label htmlFor="new-password">New password</label><input id="new-password" type="password" autoComplete="new-password" minLength={12} required value={password} onChange={(event) => setPassword(event.target.value)} /><label htmlFor="confirm-password">Confirm password</label><input id="confirm-password" type="password" autoComplete="new-password" minLength={12} required value={confirmation} onChange={(event) => setConfirmation(event.target.value)} /><button className="button button-primary auth-submit" type="submit" disabled={busy}>{busy ? "Updating…" : "Update password"}<span>→</span></button><p className="auth-help">Use at least 12 characters with upper- and lowercase letters and a number. This link expires after one hour and can only be used once.</p></form>}<p className="auth-footer"><Link href="/login">Return to sign in</Link></p></div></main>;
}
