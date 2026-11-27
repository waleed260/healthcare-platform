"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import type { FormEvent } from "react";

// Public, unauthenticated staff access-request form. The clinic comes from the URL
// slug (trusted server-side resolution), never a field the requester picks. The
// response is intentionally generic — it never reveals whether the clinic or email
// exists — and submitting grants no access or session.
export default function RequestAccessPage() {
  const params = useParams<{ clinicSlug: string }>();
  const slug = decodeURIComponent(params.clinicSlug);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const body = {
      clinic_slug: slug,
      email: String(form.get("email") ?? "").trim(),
      display_name: String(form.get("display_name") ?? "").trim() || null,
      requested_role: String(form.get("requested_role") ?? "").trim() || null,
      reason: String(form.get("reason") ?? "").trim() || null,
    };
    setSubmitting(true);
    setError(null);
    try {
      const response = await fetch("/api/v1/public/access-requests", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        cache: "no-store",
      });
      if (!response.ok && response.status !== 202) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload?.error?.message ?? "Your request could not be submitted. Please try again.");
      }
      setDone(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Your request could not be submitted.");
    } finally {
      setSubmitting(false);
    }
  }

  return <main className="auth-page"><div className="auth-panel">
    <Link className="wordmark" href="/">care<span>/</span>fully</Link>
    <div className="auth-copy">
      <p className="eyebrow">STAFF ACCESS</p>
      <h1>Request <em>access.</em></h1>
      <p>{done ? "Thanks — your request is in." : "Ask this clinic's administrator for access to the staff workspace. Every request is reviewed."}</p>
    </div>
    {done
      ? <div className="auth-form">
          <p className="auth-help">Your request has been received. If it is valid, an administrator will review it and send an invitation link to set up your account. You do not have access yet.</p>
          <Link className="button button-secondary auth-submit" href="/login">Go to sign in <span>→</span></Link>
        </div>
      : <form className="auth-form" onSubmit={submit}>
          <label htmlFor="email">Your work email<input id="email" name="email" type="email" autoComplete="email" required placeholder="you@clinic.com" /></label>
          <label htmlFor="display_name">Your name <span className="field-optional">optional</span><input id="display_name" name="display_name" maxLength={200} placeholder="Full name" /></label>
          <label htmlFor="requested_role">Role or department <span className="field-optional">optional</span><input id="requested_role" name="requested_role" maxLength={100} placeholder="e.g. Reception, Doctor" /></label>
          <label htmlFor="reason">Why do you need access? <span className="field-optional">optional</span><textarea id="reason" name="reason" maxLength={1000} rows={3} placeholder="A short note for the administrator" /></label>
          {error && <p className="auth-help" role="alert">{error}</p>}
          <button className="button button-primary auth-submit" type="submit" disabled={submitting}>{submitting ? "Submitting…" : "Request access"} <span>→</span></button>
          <p className="auth-help">An administrator decides whether to grant access, your role, and what you can do. Submitting does not create an account or sign you in.</p>
        </form>}
  </div></main>;
}
