"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, errorMessage, label, post, writeHeaders } from "../_lib/client";
import { useToast } from "../_lib/toast";
import { useConfirm } from "../_lib/confirm";

type PrivacyRequestType = "access" | "correction" | "deletion" | "restriction";
type RequestRow = { id: string; patient_id: string; request_type: string; status: string; reason: string; requested_at: string; resolved_at: string | null; resolution_note: string | null; identity_verified_at: string | null };
type ExportRow = { id: string; export_type: string; status: string; patient_id: string | null; created_at: string; completed_at: string | null; expires_at: string | null };
type Session = { permissions?: string[] };

function date(value: string): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

const statusColor: Record<string, string> = { requested: "status-new", approved: "status-paid", completed: "status-completed", rejected: "status-void", in_review: "status-pending" };

export default function PrivacyPage() {
  const [requests, setRequests] = useState<RequestRow[]>([]);
  const [exports, setExports] = useState<ExportRow[]>([]);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [patientId, setPatientId] = useState("");
  const [reason, setReason] = useState("");
  const [requestType, setRequestType] = useState<PrivacyRequestType>("access");
  const [evidence, setEvidence] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const toast = useToast();
  const confirm = useConfirm();
  const can = (p: string) => permissions.includes(p);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [session, requestData, exportData] = await Promise.all([
        api<Session>("/api/v1/auth/me"),
        api<RequestRow[]>("/api/v1/governance/privacy-requests?limit=50"),
        api<ExportRow[]>("/api/v1/governance/exports?limit=50").catch(() => [] as ExportRow[]),
      ]);
      setPermissions(session.permissions ?? []);
      setRequests(requestData ?? []);
      setExports(exportData ?? []);
    } catch (reason) {
      setError(errorMessage(reason, "The privacy workspace could not be loaded."));
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  async function createRequest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorking("create");
    setError(null);
    try {
      await post(`/api/v1/governance/patients/${patientId.trim()}/privacy-requests`, { request_type: requestType, reason: reason.trim() });
      setPatientId("");
      setReason("");
      setShowForm(false);
      toast.success("Privacy request recorded for review.");
      await load();
    } catch (reason) {
      toast.error(errorMessage(reason, "The privacy request could not be created."));
    } finally {
      setWorking(null);
    }
  }

  async function command(id: string, path: string, body?: unknown) {
    setWorking(id);
    setError(null);
    try {
      await api(`/api/v1/governance/privacy-requests/${id}/${path}`, { method: "POST", headers: writeHeaders(), body: body === undefined ? undefined : JSON.stringify(body) });
      toast.success("Privacy workflow updated.");
      await load();
    } catch (reason) {
      toast.error(errorMessage(reason, "The workflow could not be updated."));
    } finally {
      setWorking(null);
    }
  }

  async function downloadExport(item: ExportRow) {
    setWorking(item.id);
    setError(null);
    try {
      const access = await post<{ access_token: string }>(`/api/v1/governance/exports/${item.id}/signed-access`);
      const response = await fetch(`/api/v1/governance/exports/${item.id}/download`, { credentials: "include", headers: { "X-Export-Access-Token": access.access_token } });
      if (!response.ok) throw new Error("The export is not currently available.");
      const link = document.createElement("a");
      link.href = URL.createObjectURL(await response.blob());
      link.download = `export-${item.id}.json`;
      link.click();
      URL.revokeObjectURL(link.href);
      toast.success("Export downloaded.");
    } catch (reason) {
      toast.error(errorMessage(reason, "The export could not be downloaded."));
    } finally {
      setWorking(null);
    }
  }

  async function approveRequest(id: string) {
    const ok = await confirm({ title: "Approve privacy request", message: "This will allow the request to be executed. Are you sure?", confirmLabel: "Approve" });
    if (!ok) return;
    void command(id, "resolve", { expected_status: "requested", status: "approved", resolution_note: "Approved via privacy workspace." });
  }

  async function executeRequest(id: string) {
    const ok = await confirm({ title: "Execute privacy request", message: "This action may permanently modify or erase patient data. This cannot be undone.", confirmLabel: "Execute", danger: true });
    if (!ok) return;
    void command(id, "execute");
  }

  const pendingCount = requests.filter((r) => r.status === "requested").length;
  const activeExports = exports.filter((e) => e.status === "completed").length;

  return <main className="workspace-page privacy-page">
    <div className="workspace-page-header">
      <div>
        <p className="eyebrow">GOVERNANCE · IDENTITY · ERASURE</p>
        <h1>Handle privacy <em>carefully.</em></h1>
        <p className="workspace-page-intro">Record, verify, approve, and execute privacy requests through an auditable workflow.</p>
      </div>
      <div className="header-actions">
        <button className="button button-secondary" onClick={() => void load()} disabled={loading}>Refresh <span>↻</span></button>
        {can("patient.update") && <button className="button button-primary" onClick={() => setShowForm((v) => !v)}>New request <span>＋</span></button>}
      </div>
    </div>

    {error && <div className="workspace-alert" role="alert"><strong>{error}</strong><button className="ghost-button" onClick={() => void load()}>Try again <span>→</span></button></div>}

    {/* Summary strip */}
    <div className="inventory-summary" style={{ marginBottom: 20 }}>
      <div className="inventory-summary-dark"><span className="eyebrow">PENDING REVIEW</span><strong>{pendingCount}</strong><small>requests awaiting action</small></div>
      <div><span className="eyebrow">TOTAL REQUESTS</span><strong>{requests.length}</strong><small>in the register</small></div>
      <div><span className="eyebrow">READY EXPORTS</span><strong>{activeExports}</strong><small>available for download</small></div>
    </div>

    {/* New request form */}
    {showForm && <form className="surface-card" style={{ marginBottom: 16, padding: "20px" }} onSubmit={createRequest}>
      <div className="surface-card-heading"><div><p className="eyebrow">NEW REQUEST</p><h2>Start a review</h2></div></div>
      <div className="form-grid">
        <label>Patient ID<input value={patientId} onChange={(e) => setPatientId(e.target.value)} required placeholder="Authorized patient UUID" /></label>
        <label>Request type
          <select value={requestType} onChange={(e) => setRequestType(e.target.value as PrivacyRequestType)}>
            <option value="access">Access export</option>
            <option value="correction">Correction</option>
            <option value="restriction">Restriction</option>
            <option value="deletion">Deletion</option>
          </select>
        </label>
        <label>Reason<textarea value={reason} onChange={(e) => setReason(e.target.value)} required minLength={1} maxLength={1000} rows={3} placeholder="Describe the basis for this request" /></label>
      </div>
      <div className="form-actions">
        <button className="button button-secondary" type="button" onClick={() => setShowForm(false)}>Cancel</button>
        <button className="button button-primary" type="submit" disabled={working !== null}>{working === "create" ? "Recording…" : "Record request"} <span>→</span></button>
      </div>
    </form>}

    {loading && requests.length === 0 && <div className="dashboard-empty" role="status"><strong>Loading privacy workspace</strong><span>Checking your authorized register…</span></div>}

    {/* Privacy requests */}
    <section className="surface-card" style={{ marginBottom: 16 }}>
      <div className="surface-card-heading">
        <div><p className="eyebrow">REQUEST REGISTER</p><h2>Privacy requests</h2></div>
        <span className="muted-mono">{requests.length} SHOWN</span>
      </div>
      {!loading && requests.length === 0 && <div className="dashboard-empty"><strong>No requests yet</strong><span>New reviews will appear here after they are recorded.</span></div>}
      {requests.length > 0 && <div className="invoice-list">
        {requests.map((item) => <article className="invoice-row" key={item.id}>
          <div className="invoice-mark">{item.request_type === "deletion" ? "✕" : item.request_type === "access" ? "↗" : item.request_type === "correction" ? "✎" : "◇"}</div>
          <div className="invoice-main">
            <h3>{label(item.request_type)}</h3>
            <p><span className={`pipeline-status ${statusColor[item.status] ?? ""}`}>{label(item.status)}</span> · patient {item.patient_id.slice(0, 8)}…</p>
            <small>Opened {date(item.requested_at)}{item.identity_verified_at ? ` · Identity verified ${date(item.identity_verified_at)}` : ""}{item.resolved_at ? ` · Resolved ${date(item.resolved_at)}` : ""}</small>
          </div>
          <div className="invoice-actions" style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
            {!item.identity_verified_at && can("admin.clinic.manage") && <>
              <input style={{ maxWidth: 140, padding: "4px 8px", fontSize: "0.78rem", border: "1px solid var(--border-subtle, #e5e5e3)", borderRadius: 6 }} value={evidence[item.id] ?? ""} onChange={(e) => setEvidence((c) => ({ ...c, [item.id]: e.target.value }))} placeholder="Evidence note" />
              <button className="text-control" disabled={working === item.id} onClick={() => void command(item.id, "verify-identity", { evidence_note: evidence[item.id] ?? "" })}>Verify</button>
            </>}
            {item.status === "requested" && can("admin.clinic.manage") && <button className="text-control" disabled={working === item.id} onClick={() => void approveRequest(item.id)}>Approve</button>}
            {item.status === "approved" && can("admin.clinic.manage") && <button className="button button-secondary" style={{ fontSize: "0.78rem", padding: "4px 10px" }} disabled={working === item.id} onClick={() => void executeRequest(item.id)}>Execute</button>}
          </div>
        </article>)}
      </div>}
    </section>

    {/* Export jobs */}
    <section className="surface-card">
      <div className="surface-card-heading">
        <div><p className="eyebrow">PRIVATE DELIVERY</p><h2>Export jobs</h2></div>
        <span className="muted-mono">{exports.length} SHOWN</span>
      </div>
      {exports.length === 0
        ? <div className="dashboard-empty"><strong>No export jobs</strong><span>Approved access requests appear here when queued.</span></div>
        : <div className="invoice-list">
          {exports.map((item) => <article className="invoice-row" key={item.id}>
            <div className="invoice-mark">↓</div>
            <div className="invoice-main">
              <h3>{label(item.export_type)}</h3>
              <p><span className={`pipeline-status ${statusColor[item.status] ?? ""}`}>{label(item.status)}</span>{item.patient_id ? ` · patient ${item.patient_id.slice(0, 8)}…` : " · Clinic audit"}</p>
              <small>Created {date(item.created_at)}{item.completed_at ? ` · Completed ${date(item.completed_at)}` : ""}</small>
            </div>
            <div className="invoice-actions">
              {item.status === "completed" && can("patient.export") && <button className="button button-secondary" style={{ fontSize: "0.78rem", padding: "4px 10px" }} disabled={working === item.id} onClick={() => void downloadExport(item)}>{working === item.id ? "Preparing…" : "Download"}</button>}
            </div>
          </article>)}
        </div>}
    </section>
  </main>;
}
