"use client";

import Link from "next/link";
import { FormEvent, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { csrfToken, safeNextPath } from "../(authenticated)/_lib/client";

type Phase = "login" | "mfa" | "enroll";

async function freshCsrf(): Promise<string> {
  try {
    const r = await fetch("/api/v1/auth/csrf", { method: "POST", credentials: "include" });
    const body = await r.json().catch(() => null) as { data?: { csrf_token?: string } } | null;
    return body?.data?.csrf_token ?? csrfToken();
  } catch { return csrfToken(); }
}

async function apiMessage(response: Response): Promise<string> {
  const payload = await response.json().catch(() => null) as { error?: { message?: string } } | null;
  return payload?.error?.message ?? (response.status === 401 ? "Your credentials or verification code are not correct." : "Something went wrong. Try again shortly.");
}

async function checkServerReady(): Promise<boolean> {
  try {
    const r = await fetch("/health/ready", { cache: "no-store", signal: AbortSignal.timeout(5000) });
    return r.ok;
  } catch { return false; }
}

export default function LoginPage() {
  const router = useRouter();

  const nextPath = safeNextPath(
    typeof window === "undefined" ? null : new URLSearchParams(window.location.search).get("next"),
  );
  const [phase, setPhase] = useState<Phase>("login");
  const [recovery, setRecovery] = useState(false);
  const [enrollment, setEnrollment] = useState<{ secret: string; recovery_codes: string[] } | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [googleEnabled, setGoogleEnabled] = useState(false);
  const [serverReady, setServerReady] = useState<boolean | null>(null);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  async function beginEnrollment() {
    const token = await freshCsrf();
    const enrollmentResponse = await fetch("/api/v1/auth/mfa/enroll", { method: "POST", headers: { "X-CSRF-Token": token }, credentials: "include" });
    if (!enrollmentResponse.ok) throw new Error(await apiMessage(enrollmentResponse));
    setEnrollment(await enrollmentResponse.json() as { secret: string; recovery_codes: string[] });
    setPhase("enroll");
  }

  useEffect(() => {
    let mounted = true;
    async function probe() {
      const ready = await checkServerReady();
      if (!mounted) return;
      setServerReady(ready);
      if (!ready) pollRef.current = setTimeout(probe, 3000);
      else {
        void fetch("/api/v1/auth/google/config", { cache: "no-store" }).then((r) => r.ok ? r.json() : null).then((p) => { if (mounted) setGoogleEnabled(p?.data?.enabled === true); }).catch(() => undefined);
      }
    }
    void probe();
    return () => { mounted = false; if (pollRef.current) clearTimeout(pollRef.current); };
  }, []);

  useEffect(() => {
    if (!serverReady) return;
    const outcome = new URLSearchParams(window.location.search).get("google");
    if (!outcome) return;
    window.history.replaceState(null, "", "/login");
    if (outcome === "ok") router.push(nextPath ?? "/dashboard");
    else if (outcome === "mfa") setPhase("mfa");
    else if (outcome === "enroll") void beginEnrollment().catch((reason) => setError(reason instanceof Error ? reason.message : "Unable to start MFA enrollment."));
    else setError(outcome === "no_account" ? "No active workspace account matches that Google email. Ask your clinic administrator for an invitation." : outcome === "unverified" ? "Google could not verify that email address." : "Google sign-in could not be completed. Try again.");
  }, [serverReady]);

  async function submitLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true); setError(null);
    try {
      const delays = [1500, 3000, 5000];
      let response: Response | null = null;
      for (let attempt = 0; attempt <= delays.length; attempt++) {
        response = await fetch("/api/v1/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, credentials: "include", body: JSON.stringify({ email, password }) });
        if (response.status !== 503 || attempt === delays.length) break;
        await new Promise((r) => setTimeout(r, delays[attempt]));
      }
      if (!response || !response.ok) {
        if (response && response.status === 503) throw new Error("The clinic server is still starting up. Please wait a moment and try again.");
        throw new Error(response ? await apiMessage(response) : "Unable to reach the clinic server.");
      }
      const payload = await response.json() as { data: { mfa_required: boolean; mfa_enrollment_required: boolean } };
      if (payload.data.mfa_enrollment_required) {
        const token = await freshCsrf();
        const enrollmentResponse = await fetch("/api/v1/auth/mfa/enroll", { method: "POST", headers: { "X-CSRF-Token": token }, credentials: "include" });
        if (!enrollmentResponse.ok) throw new Error(await apiMessage(enrollmentResponse));
        const enrollmentPayload = await enrollmentResponse.json() as { secret: string; recovery_codes: string[] };
        setEnrollment(enrollmentPayload);
        setPhase("enroll");
      } else if (payload.data.mfa_required) setPhase("mfa"); else router.push(nextPath ?? "/dashboard");
    } catch (reason) {
      if (reason instanceof TypeError && reason.message.includes("fetch")) setError("Unable to reach the clinic server. It may still be starting up — please try again in a moment.");
      else setError(reason instanceof Error ? reason.message : "Unable to sign in.");
    }
    finally { setBusy(false); }
  }

  async function submitMfa(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true); setError(null);
    try {
      const token = await freshCsrf();
      const response = await fetch(`/api/v1/auth/mfa/${recovery ? "recover" : "verify"}`, { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": token }, credentials: "include", body: JSON.stringify({ code }) });
      if (!response.ok) throw new Error(await apiMessage(response));
      router.push(nextPath ?? "/dashboard");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to verify this code."); }
    finally { setBusy(false); }
  }

  return <main className="auth-page"><div className="auth-panel"><Link className="wordmark" href="/">care<span>/</span>fully</Link><div className="auth-copy"><p className="eyebrow">SECURE CLINIC WORKSPACE</p><h1>{phase === "login" ? <>Welcome<br /><em>back.</em></> : phase === "enroll" ? <>Secure your<br /><em>workspace.</em></> : <>One more<br /><em>step.</em></>}</h1><p>{phase === "login" ? "Sign in to continue to your clinic workspace." : phase === "enroll" ? "Set up an authenticator before continuing. Save the recovery codes somewhere secure; they are shown only once." : recovery ? "Enter one unused recovery code to continue." : "Enter the verification code from your authenticator app."}</p></div>
    {serverReady === false && <div className="workspace-alert workspace-alert-connecting" role="status">Connecting to your clinic server… This usually takes about a minute after the system starts.</div>}
    {error && <div className="workspace-alert" role="alert">{error}</div>}
    {phase === "login" ? <form className="auth-form" onSubmit={submitLogin}><label htmlFor="email">Clinic email</label><input id="email" type="email" autoComplete="username" required value={email} onChange={(event) => setEmail(event.target.value)} /><label htmlFor="password">Password</label><input id="password" type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} /><button className="button button-primary auth-submit" type="submit" disabled={busy || serverReady === false}>{serverReady === false ? "Waiting for server…" : busy ? "Signing in…" : "Sign in"}<span>→</span></button>{googleEnabled && <button className="button button-secondary auth-submit" type="button" disabled={serverReady === false} onClick={() => window.location.assign("/api/v1/auth/google/start")}>Continue with Google <span>→</span></button>}<p className="auth-help">Forgot your password? Contact your clinic administrator. This workspace does not send recovery email or SMS.</p></form> : phase === "enroll" ? <><div className="auth-help"><strong>Authenticator secret</strong><code>{enrollment?.secret}</code><strong>Recovery codes</strong><code>{enrollment?.recovery_codes.join("\n")}</code></div><form className="auth-form" onSubmit={submitMfa}><label htmlFor="code">First authenticator code</label><input id="code" inputMode="numeric" autoComplete="one-time-code" minLength={6} required value={code} onChange={(event) => setCode(event.target.value)} /><button className="button button-primary auth-submit" type="submit" disabled={busy}>{busy ? "Checking…" : "Verify and continue"}<span>→</span></button></form></> : <form className="auth-form" onSubmit={submitMfa}><label htmlFor="code">{recovery ? "Recovery code" : "Authenticator code"}</label><input id="code" inputMode="numeric" autoComplete="one-time-code" minLength={recovery ? 8 : 6} required value={code} onChange={(event) => setCode(event.target.value)} /><button className="button button-primary auth-submit" type="submit" disabled={busy}>{busy ? "Checking…" : "Continue"}<span>→</span></button><button className="text-link auth-switch" type="button" onClick={() => { setRecovery(!recovery); setCode(""); }}>{recovery ? "Use authenticator code" : "Use a recovery code"}</button></form>}
    <p className="auth-footer"><Link href="/">Return to carefully</Link></p></div></main>;
}
