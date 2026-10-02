"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, errorMessage, patch, post } from "../(authenticated)/_lib/client";

type Clinic = { name: string; timezone: string; locale: string; default_currency?: string; version: number };
type Specialty = { id: string; code: string; name: string; enabled?: boolean };
const CURRENCIES = ["PKR", "USD", "EUR", "GBP", "AED", "SAR", "INR"];

/** Optional blueprint §5.1 first-login steps beyond the core checklist: profile, currency, specialties, staff, website. */
export default function SetupExtras() {
  const [clinic, setClinic] = useState<Clinic | null>(null);
  const [specialties, setSpecialties] = useState<Specialty[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [clinicRow, specialtyRows] = await Promise.all([api<Clinic>("/api/v1/clinic").catch(() => null), api<Specialty[]>("/api/v1/specialties/library").catch(() => [])]);
      setClinic(clinicRow && typeof clinicRow === "object" && "version" in clinicRow ? clinicRow : null);
      setSpecialties(Array.isArray(specialtyRows) ? specialtyRows : []);
    } catch (reason) { setError(errorMessage(reason, "Optional setup steps could not be loaded.")); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const run = async (key: string, action: () => Promise<unknown>, success: string) => {
    setBusy(key); setError(null); setNotice(null);
    try { await action(); setNotice(success); await load(); } catch (reason) { setError(errorMessage(reason, "That step could not be saved.")); } finally { setBusy(null); }
  };
  const saveProfile = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!clinic) return;
    const form = new FormData(event.currentTarget);
    void run("profile", () => patch("/api/v1/clinic", { expected_version: clinic.version, name: String(form.get("name")).trim(), timezone: String(form.get("timezone")).trim(), locale: String(form.get("locale")).trim(), default_currency: String(form.get("currency")) }), "Clinic profile saved.");
  };
  const invite = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const target = event.currentTarget;
    const email = String(new FormData(target).get("email")).trim();
    void run("invite", async () => { await post("/api/v1/staff/invitations", { email }); target.reset(); }, `Invitation created for ${email}.`);
  };

  if (!clinic && specialties.length === 0) return null;
  return <section className="setup-extras" aria-label="More ways to set up">
    <div className="setup-intro"><p className="eyebrow">NEXT · MAKE IT COMPLETE</p><h2>Profile, specialties, team and website.</h2></div>
    {error && <div className="workspace-alert" role="alert"><span>{error}</span></div>}
    {notice && <p className="field-note" aria-live="polite">{notice}</p>}
    <div className="setup-actions-grid">
      {clinic && <form className="setup-card" onSubmit={saveProfile}><p className="eyebrow">PROFILE</p><h2>Clinic details &amp; currency</h2>
        <label>Clinic name<input name="name" required maxLength={200} defaultValue={clinic.name} /></label>
        <label>Timezone<input name="timezone" required maxLength={80} defaultValue={clinic.timezone} /></label>
        <label>Locale<input name="locale" required pattern="[a-z]{2}(-[A-Z]{2})?" defaultValue={clinic.locale} /></label>
        <label>Currency<select name="currency" defaultValue={clinic.default_currency ?? "PKR"}>{CURRENCIES.map((code) => <option key={code}>{code}</option>)}</select></label>
        <button className="button button-primary" type="submit" disabled={busy !== null}>{busy === "profile" ? "Saving…" : "Save profile"}</button>
        <p className="setup-card-copy">Add your logo in the <Link href="/website">website editor</Link>.</p></form>}
      {specialties.length > 0 && <div className="setup-card"><p className="eyebrow">SPECIALTIES</p><h2>What do you practise?</h2>
        {specialties.map((item) => <div className="theme-row" key={item.id}><span>{item.name}</span>{item.enabled ? <span className="pipeline-status status-paid">Enabled</span> : <button className="text-control" disabled={busy !== null} onClick={() => void run(item.code, () => post("/api/v1/specialties/enable", { code: item.code }), `${item.name} enabled.`)}>Enable</button>}</div>)}
        <p className="setup-card-copy">Need one that isn’t listed? Request access from <Link href="/manage">Manage</Link>.</p></div>}
      <form className="setup-card" onSubmit={invite}><p className="eyebrow">TEAM</p><h2>Invite your staff</h2><label>Email<input name="email" type="email" required placeholder="doctor@clinic.com" /></label><button className="button button-primary" type="submit" disabled={busy !== null}>{busy === "invite" ? "Sending…" : "Send invitation"}</button><p className="setup-card-copy">Staff sign in with their own credentials — no shared logins.</p></form>
      <div className="setup-card"><p className="eyebrow">WEBSITE</p><h2>Launch your site</h2><p className="setup-card-copy">Pick a specialty template, review the pages it adds, then publish. Services, doctors and branches appear automatically.</p><Link className="button button-secondary" href="/website">Open website editor <span>→</span></Link></div>
    </div>
  </section>;
}
