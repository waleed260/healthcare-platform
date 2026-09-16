"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";

type Patient = { id: string; patient_number: string; full_name: string; normalized_email: string | null; normalized_phone: string | null; status: string; version: number };
type PatientPage = { data?: Patient[]; meta?: { next_cursor?: string | null } };

function responseMessage(response: Response, payload: any): string {
  if (payload?.error?.message) return payload.error.message;
  if (response.status === 401) return "Your session has expired. Sign in again to continue.";
  if (response.status === 403) return "Your role does not include patient access.";
  return "The patient list could not be loaded.";
}

export default function PatientsPage() {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [search, setSearch] = useState("");
  const [activeSearch, setActiveSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [refreshedAt, setRefreshedAt] = useState<Date | null>(null);
  const loadPatients = useCallback(async (term: string, cursor: string | null = null, append = false) => {
    setLoading(true); setError(null);
    try {
      const params = new URLSearchParams();
      if (term) params.set("search", term);
      if (cursor) params.set("cursor", cursor);
      const query = params.toString();
      const response = await fetch(`/api/v1/patients${query ? `?${query}` : ""}`, { credentials: "include", cache: "no-store" });
      const payload = (await response.json()) as PatientPage & { error?: { message?: string } };
      if (!response.ok) throw new Error(responseMessage(response, payload));
      setPatients((current) => append ? [...current, ...(payload.data ?? [])] : (payload.data ?? []));
      setNextCursor(payload.meta?.next_cursor ?? null); setRefreshedAt(new Date());
    } catch (reason) { setError(reason instanceof Error ? reason.message : "The patient list could not be loaded."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void loadPatients(""); }, [loadPatients]);
  function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const term = search.trim(); setActiveSearch(term); void loadPatients(term); }
  return <main className="dashboard-page"><header className="dash-header shell"><Link className="wordmark" href="/">care<span>/</span>fully</Link><div className="clinic-chip" aria-label="Clinic workspace session"><span className="clinic-avatar">VC</span><span>Clinic workspace</span></div></header><div className="dashboard shell"><aside className="sidebar"><p className="eyebrow">WORKSPACE</p><nav aria-label="Workspace navigation"><Link className="side-link" href="/dashboard">◈ <span>Overview</span></Link><Link className="side-link active" href="/patients" aria-current="page">○ <span>Patients</span></Link><a className="side-link" href="/dashboard#schedule">◷ <span>Schedule</span></a><a className="side-link" href="/dashboard#followups">↗ <span>Follow-ups</span></a><a className="side-link" href="/dashboard#website">✦ <span>Website</span></a></nav></aside><section className="dash-content patient-content" aria-busy={loading}><div className="dash-topline"><div><p className="eyebrow">CLINIC RECORDS · SCOPED ACCESS</p><h1>People, <em>carefully.</em></h1></div><button className="button button-primary" type="button" onClick={() => void loadPatients(activeSearch)} disabled={loading}>Refresh <span>↻</span></button></div><div className="patient-toolbar"><form onSubmit={submit} role="search" aria-label="Search patients"><label htmlFor="patient-search">Search name, email, or phone</label><div className="patient-search-row"><input id="patient-search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Start typing a patient detail" /><button className="button button-primary" type="submit" disabled={loading}>Search <span>→</span></button></div></form><p className="privacy-caption">Only records in your authorized clinic scope appear here. Private clinical notes are not shown in this list.</p></div>{error && <div className="workspace-alert" role="alert"><strong>{error}</strong><button className="ghost-button" type="button" onClick={() => void loadPatients(activeSearch)}>Try again <span>→</span></button></div>}<div className="patient-card"><div className="card-heading"><div><p className="eyebrow">PATIENT DIRECTORY</p><h2>{activeSearch ? `Results for “${activeSearch}”` : "All active patients"}</h2></div><span className="directory-count">{loading ? "…" : `${patients.length} shown`}</span></div>{loading && patients.length === 0 && <div className="dashboard-empty" role="status"><strong>Loading patient records</strong><span>Checking your authorized clinic scope…</span></div>}{!loading && !error && patients.length === 0 && <div className="dashboard-empty"><strong>{activeSearch ? "No matching patients" : "No active patients yet"}</strong><span>{activeSearch ? "Try a different name or contact detail." : "New records will appear here after a booking or staff entry."}</span></div>}{patients.length > 0 && <div className="patient-list" role="list">{patients.map((patient) => <Link className="patient-row" href={`/patients/${patient.id}`} key={patient.id} role="listitem"><span className="patient-initial" aria-hidden="true">{patient.full_name.trim().charAt(0).toUpperCase()}</span><span className="patient-main"><strong>{patient.full_name}</strong><small>{patient.patient_number} · {patient.status}</small></span><span className="patient-contact">{patient.normalized_email ?? patient.normalized_phone ?? "No contact recorded"}</span><span className="row-arrow" aria-hidden="true">→</span></Link>)}</div>}{nextCursor && !error && <button className="button button-secondary patient-load-more" type="button" onClick={() => void loadPatients(activeSearch, nextCursor, true)} disabled={loading} aria-label="Load more patient records">{loading ? "Loading more…" : "Load more patients"}<span>↓</span></button>}{refreshedAt && <p className="stale-note">Updated {refreshedAt.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}</p>}</div></section></div></main>;
}
