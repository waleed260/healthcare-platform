"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

type Phase = "login" | "mfa" | "enroll";

function csrfToken(): string {
  const match = document.cookie.match(/(?:^|; )csrf_token=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

async function apiMessage(response: Response): Promise<string> {
  const payload = await response.json().catch(() => null) as { error?: { message?: string } } | null;
  return payload?.error?.message ?? (response.status === 401 ? "Your credentials or verification code are not correct." : "Something went wrong. Try again shortly.");
}

export default function LoginPage() {
  const router = useRouter();
  const [phase, setPhase] = useState<Phase>("login");
  const [recovery, setRecovery] = useState(false);
  const [enrollment, setEnrollment] = useState<{ secret: string; recovery_codes: string[] } | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submitLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true); setError(null);
    try {
      const response = await fetch("/api/v1/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, credentials: "include", body: JSON.stringify({ email, password }) });
      if (!response.ok) throw new Error(await apiMessage(response));
      const payload = await response.json() as { data: { mfa_required: boolean; mfa_enrollment_required: boolean } };
      if (payload.data.mfa_enrollment_required) {
        const enrollmentResponse = await fetch("/api/v1/auth/mfa/enroll", { method: "POST", headers: { "X-CSRF-Token": csrfToken() }, credentials: "include" });
        if (!enrollmentResponse.ok) throw new Error(await apiMessage(enrollmentResponse));
        const enrollmentPayload = await enrollmentResponse.json() as { secret: string; recovery_codes: string[] };
        setEnrollment(enrollmentPayload);
        setPhase("enroll");
      } else if (payload.data.mfa_required) setPhase("mfa"); else router.push("/dashboard");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to sign in."); }
    finally { setBusy(false); }
  }

  async function submitMfa(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true); setError(null);
    try {
      const response = await fetch(`/api/v1/auth/mfa/${recovery ? "recover" : "verify"}`, { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken() }, credentials: "include", body: JSON.stringify({ code }) });
      if (!response.ok) throw new Error(await apiMessage(response));
      router.push("/dashboard");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to verify this code."); }
    finally { setBusy(false); }
  }

  return <main className="auth-page"><div className="auth-panel"><Link className="wordmark" href="/">care<span>/</span>fully</Link><div className="auth-copy"><p className="eyebrow">SECURE CLINIC WORKSPACE</p><h1>{phase === "login" ? <>Welcome<br /><em>back.</em></> : phase === "enroll" ? <>Secure your<br /><em>workspace.</em></> : <>One more<br /><em>step.</em></>}</h1><p>{phase === "login" ? "Sign in to continue to your clinic workspace." : phase === "enroll" ? "Set up an authenticator before continuing. Save the recovery codes somewhere secure; they are shown only once." : recovery ? "Enter one unused recovery code to continue." : "Enter the verification code from your authenticator app."}</p></div>
    {error && <div className="workspace-alert" role="alert">{error}</div>}
    {phase === "login" ? <form className="auth-form" onSubmit={submitLogin}><label htmlFor="email">Clinic email</label><input id="email" type="email" autoComplete="username" required value={email} onChange={(event) => setEmail(event.target.value)} /><label htmlFor="password">Password</label><input id="password" type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} /><button className="button button-primary auth-submit" type="submit" disabled={busy}>{busy ? "Signing in…" : "Sign in"}<span>→</span></button><p className="auth-help">Forgot your password? Contact your clinic administrator. This workspace does not send recovery email or SMS.</p></form> : phase === "enroll" ? <><div className="auth-help"><strong>Authenticator secret</strong><code>{enrollment?.secret}</code><strong>Recovery codes</strong><code>{enrollment?.recovery_codes.join("\n")}</code></div><form className="auth-form" onSubmit={submitMfa}><label htmlFor="code">First authenticator code</label><input id="code" inputMode="numeric" autoComplete="one-time-code" minLength={6} required value={code} onChange={(event) => setCode(event.target.value)} /><button className="button button-primary auth-submit" type="submit" disabled={busy}>{busy ? "Checking…" : "Verify and continue"}<span>→</span></button></form></> : <form className="auth-form" onSubmit={submitMfa}><label htmlFor="code">{recovery ? "Recovery code" : "Authenticator code"}</label><input id="code" inputMode="numeric" autoComplete="one-time-code" minLength={recovery ? 8 : 6} required value={code} onChange={(event) => setCode(event.target.value)} /><button className="button button-primary auth-submit" type="submit" disabled={busy}>{busy ? "Checking…" : "Continue"}<span>→</span></button><button className="text-link auth-switch" type="button" onClick={() => { setRecovery(!recovery); setCode(""); }}>{recovery ? "Use authenticator code" : "Use a recovery code"}</button></form>}
    <p className="auth-footer"><Link href="/">Return to carefully</Link></p></div></main>;
}
