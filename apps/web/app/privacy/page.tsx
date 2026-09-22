"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import type { PrivacyRequestCreateRequestTypeValue } from "../../../../packages/contracts/openapi-types";

type RequestRow = { id: string; patient_id: string; request_type: string; status: string; reason: string; requested_at: string; identity_verified_at: string | null };
type ExportRow = { id: string; export_type: string; status: string; patient_id: string | null; created_at: string; expires_at: string | null };

function csrf(): string { return document.cookie.split("; ").find((item) => item.startsWith("csrf_token="))?.split("=")[1] ?? ""; }
function date(value: string): string { return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)); }
async function read(response: Response): Promise<any> { const payload = await response.json().catch(() => ({})); if (!response.ok) throw new Error(payload?.error?.message ?? "The privacy workspace could not complete that action."); return payload.data; }

export default function PrivacyPage() {
  const [requests, setRequests] = useState<RequestRow[]>([]);
  const [exports, setExports] = useState<ExportRow[]>([]);
  const [patientId, setPatientId] = useState("");
  const [reason, setReason] = useState("");
  const [requestType, setRequestType] = useState<PrivacyRequestCreateRequestTypeValue>("access");
  const [evidence, setEvidence] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const [requestResponse, exportResponse] = await Promise.all([
        fetch("/api/v1/governance/privacy-requests?limit=50", { credentials: "include", cache: "no-store" }),
        fetch("/api/v1/governance/exports?limit=50", { credentials: "include", cache: "no-store" }),
      ]);
      setRequests((await read(requestResponse) ?? []) as RequestRow[]);
      setExports((await read(exportResponse) ?? []) as ExportRow[]);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "The privacy workspace could not be loaded."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  async function createRequest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setWorking("create"); setError(null); setNotice(null);
    try {
      await read(await fetch(`/api/v1/governance/patients/${patientId.trim()}/privacy-requests`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf() }, body: JSON.stringify({ request_type: requestType, reason: reason.trim() }) }));
      setPatientId(""); setReason(""); setNotice("Privacy request recorded for review."); await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "The privacy request could not be created."); }
    finally { setWorking(null); }
  }

  async function command(id: string, path: string, body?: unknown) {
    setWorking(id); setError(null); setNotice(null);
    try { await read(await fetch(`/api/v1/governance/privacy-requests/${id}/${path}`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf() }, body: body === undefined ? undefined : JSON.stringify(body) })); setNotice("Privacy workflow updated and audited."); await load(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "The privacy workflow could not be updated."); }
    finally { setWorking(null); }
  }

  async function downloadExport(item: ExportRow) {
    setWorking(item.id); setError(null);
    try {
      const access = await read(await fetch(`/api/v1/governance/exports/${item.id}/signed-access`, { method: "POST", credentials: "include", headers: { "X-CSRF-Token": csrf() } })) as { access_token: string };
      const response = await fetch(`/api/v1/governance/exports/${item.id}/download`, { credentials: "include", headers: { "X-Export-Access-Token": access.access_token } });
      if (!response.ok) throw new Error("The export is not currently available.");
      const link = window.document.createElement("a"); link.href = URL.createObjectURL(await response.blob()); link.download = `export-${item.id}.json`; link.click(); URL.revokeObjectURL(link.href);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "The export could not be downloaded."); }
    finally { setWorking(null); }
  }

  return <main className="dashboard-page"><header className="dash-header shell"><Link className="wordmark" href="/">care<span>/</span>fully</Link><div className="clinic-chip" aria-label="Clinic privacy workspace"><span className="clinic-avatar">PR</span><span>Privacy workspace</span></div></header><div className="dashboard shell"><aside className="sidebar"><p className="eyebrow">WORKSPACE</p><nav aria-label="Workspace navigation"><Link className="side-link" href="/dashboard">◈ <span>Overview</span></Link><Link className="side-link" href="/patients">○ <span>Patients</span></Link><Link className="side-link" href="/operations">↗ <span>Operations</span></Link><Link className="side-link active" href="/privacy" aria-current="page">◇ <span>Privacy</span></Link></nav></aside><section className="dash-content privacy-content" aria-busy={loading}><div className="dash-topline"><div><p className="eyebrow">IDENTITY · EXPORTS · ERASURE</p><h1>Handle privacy <em>carefully.</em></h1></div><button className="button button-primary" type="button" onClick={() => void load()} disabled={loading}>Refresh <span>↻</span></button></div><p className="queue-intro">Record, verify, approve, and execute privacy requests through an auditable workflow. Patient identifiers are entered only for the protected server-side lookup.</p>{error && <div className="workspace-alert" role="alert"><strong>{error}</strong><button className="ghost-button" type="button" onClick={() => void load()}>Try again <span>→</span></button></div>}{notice && <div className="workspace-alert governance-notice" role="status">{notice}</div>}<div className="privacy-grid"><form className="detail-card privacy-form" onSubmit={createRequest}><p className="eyebrow">NEW REQUEST</p><h2>Start a review</h2><label htmlFor="privacy-patient">Patient ID</label><input id="privacy-patient" value={patientId} onChange={(event) => setPatientId(event.target.value)} required placeholder="Authorized patient UUID" /><label htmlFor="privacy-type">Request type</label><select id="privacy-type" value={requestType} onChange={(event) => setRequestType(event.target.value as PrivacyRequestCreateRequestTypeValue)}><option value="access">Access export</option><option value="correction">Correction</option><option value="restriction">Restriction</option><option value="deletion">Deletion</option></select><label htmlFor="privacy-reason">Reason</label><textarea id="privacy-reason" value={reason} onChange={(event) => setReason(event.target.value)} required minLength={1} maxLength={1000} rows={4} placeholder="Synthetic workflow reason" /><button className="button button-primary" type="submit" disabled={working !== null}>{working === "create" ? "Recording…" : "Record request"}<span>→</span></button><p className="privacy-caption">Identity verification, legal-hold checks, approval, and completion remain server-side gates.</p></form><section className="detail-card"><div className="card-heading"><div><p className="eyebrow">REQUEST REGISTER</p><h2>Privacy requests</h2></div><span className="directory-count">{requests.length} shown</span></div>{loading && requests.length === 0 && <div className="dashboard-empty" role="status"><strong>Loading privacy requests</strong><span>Checking your authorized register…</span></div>}{!loading && requests.length === 0 && <div className="dashboard-empty"><strong>No requests yet</strong><span>New reviews will appear here after they are recorded.</span></div>}{requests.length > 0 && <div className="operations-list">{requests.map((item) => <article className="operations-row privacy-row" key={item.id}><div><strong>{item.request_type.replaceAll("_", " ")} · {item.status}</strong><small>{item.patient_id} · opened {date(item.requested_at)}</small>{item.identity_verified_at && <small>Identity verified {date(item.identity_verified_at)}</small>}</div><div className="privacy-actions">{!item.identity_verified_at && <><input aria-label={`Identity evidence for ${item.id}`} value={evidence[item.id] ?? ""} onChange={(event) => setEvidence((current) => ({ ...current, [item.id]: event.target.value }))} placeholder="Evidence note" /><button className="ghost-button" type="button" onClick={() => void command(item.id, "verify-identity", { evidence_note: evidence[item.id] ?? "" })} disabled={working === item.id}>Verify</button></>}{item.status === "requested" && <button className="ghost-button" type="button" onClick={() => void command(item.id, "resolve", { expected_status: "requested", status: "approved", resolution_note: "Synthetic approval recorded for review." })} disabled={working === item.id}>Approve</button>}{item.status === "approved" && <button className="button button-secondary" type="button" onClick={() => void command(item.id, "execute")} disabled={working === item.id}>Execute approved request</button>}</div></article>)}</div>}</section></div><section className="detail-card export-card"><div className="card-heading"><div><p className="eyebrow">PRIVATE DELIVERY</p><h2>Export jobs</h2></div><span className="directory-count">{exports.length} shown</span></div>{exports.length === 0 ? <div className="dashboard-empty"><strong>No export jobs</strong><span>Approved access requests appear here when queued.</span></div> : <div className="operations-list">{exports.map((item) => <article className="operations-row" key={item.id}><div><strong>{item.export_type.replaceAll("_", " ")} · {item.status}</strong><small>{item.patient_id ?? "Clinic audit"} · created {date(item.created_at)}</small></div>{item.status === "completed" && <button className="button button-secondary" type="button" onClick={() => void downloadExport(item)} disabled={working === item.id}>{working === item.id ? "Preparing…" : "Download once"}</button>}</article>)}</div>}</section></section></div></main>;
}
