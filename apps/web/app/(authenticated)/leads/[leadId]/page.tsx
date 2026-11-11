"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { api, apiPage, post, patch, errorMessage } from "../../_lib/client";
import { useToast } from "../../_lib/toast";
import { useConfirm } from "../../_lib/confirm";

type Lead = { id: string; full_name: string; normalized_email: string | null; normalized_phone: string | null; source: string; campaign: string | null; status: string; specialty_id: string | null; requested_service_id: string | null; branch_id: string | null; assigned_to_user_id: string | null; converted_to_patient_id: string | null; lost_reason: string | null; notes: string | null; created_at: string; updated_at: string; version: number };
type Activity = { id: string; lead_id: string; actor_user_id: string; kind: string; body: string; due_at: string | null; created_at: string };
type Specialty = { id: string; name: string };
type Service = { id: string; name: string };
type Branch = { id: string; name: string };
type Session = { permissions?: string[] };

const stages = ["new", "contacted", "qualified", "appointment_booked", "visited", "converted", "lost"];
const activityKinds = ["call", "note", "message", "follow_up"] as const;
type ActivityKind = (typeof activityKinds)[number];
const statusLabel = (s: string) => s.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
const formatDateTime = (v: string) => new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(v));
const formatDate = (v: string) => new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(v));

export default function LeadDetailPage() {
  const { leadId } = useParams<{ leadId: string }>();
  const router = useRouter();
  const toast = useToast();
  const confirm = useConfirm();

  const [lead, setLead] = useState<Lead | null>(null);
  const [specialties, setSpecialties] = useState<Specialty[]>([]);
  const [services, setServices] = useState<Service[]>([]);
  const [branches, setBranches] = useState<Branch[]>([]);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [edit, setEdit] = useState({ full_name: "", email: "", phone: "", campaign: "", specialty_id: "", requested_service_id: "", branch_id: "", notes: "" });

  // Activity state
  const [activities, setActivities] = useState<Activity[]>([]);
  const [activitiesCursor, setActivitiesCursor] = useState<string | null>(null);
  const [activitiesLoading, setActivitiesLoading] = useState(false);
  const [actKind, setActKind] = useState<ActivityKind>("call");
  const [actBody, setActBody] = useState("");
  const [actDueAt, setActDueAt] = useState("");
  const [actBusy, setActBusy] = useState(false);

  const can = (p: string) => permissions.includes(p);
  const specialtyNames = useMemo(() => new Map(specialties.map((s) => [s.id, s.name])), [specialties]);
  const branchNames = useMemo(() => new Map(branches.map((b) => [b.id, b.name])), [branches]);

  const loadLead = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [session, leadData, specialtyData, serviceData, branchData] = await Promise.all([
        api<Session>("/api/v1/auth/me"),
        api<Lead>(`/api/v1/leads/${leadId}`),
        api<Specialty[]>("/api/v1/specialties"),
        api<Service[]>("/api/v1/services?limit=100").catch(() => null),
        api<Branch[]>("/api/v1/branches?limit=100").catch(() => null),
      ]);
      setPermissions(session.permissions ?? []);
      setLead(leadData);
      setSpecialties(specialtyData ?? []);
      setServices(serviceData ?? []);
      setBranches(branchData ?? []);
    } catch (reason) {
      setError(errorMessage(reason, "This lead could not be loaded."));
    } finally {
      setLoading(false);
    }
  }, [leadId]);

  const loadActivities = useCallback(async (cursor: string | null = null, append = false) => {
    setActivitiesLoading(true);
    try {
      const params = new URLSearchParams({ limit: "50" });
      if (cursor) params.set("cursor", cursor);
      const page = await apiPage<Activity>(`/api/v1/leads/${leadId}/activities?${params.toString()}`);
      setActivities((prev) => append ? [...prev, ...page.data] : page.data);
      setActivitiesCursor(page.nextCursor);
    } catch (reason) { toast.error(errorMessage(reason, "Activities could not be loaded.")); }
    finally { setActivitiesLoading(false); }
  }, [leadId, toast]);

  useEffect(() => { void loadLead(); void loadActivities(); }, [loadLead, loadActivities]);

  async function updateStatus(newStatus: string) {
    if (!lead) return;
    setBusy(true);
    try {
      await patch(`/api/v1/leads/${leadId}`, { expected_version: lead.version, status: newStatus });
      toast.success(`Stage updated to ${statusLabel(newStatus)}.`);
      await loadLead();
    } catch (reason) { toast.error(errorMessage(reason, "The lead could not be updated.")); }
    finally { setBusy(false); }
  }

  async function archiveLead() {
    if (!lead) return;
    const yes = await confirm({ message: `Archive "${lead.full_name}"? It will be removed from the pipeline.` });
    if (!yes) return;
    setBusy(true);
    try {
      await post(`/api/v1/leads/${leadId}/archive`, {});
      toast.success("Lead archived.");
      router.push("/leads");
    } catch (reason) { toast.error(errorMessage(reason, "The lead could not be archived.")); setBusy(false); }
  }

  function openEdit() {
    if (!lead) return;
    setEdit({
      full_name: lead.full_name,
      email: lead.normalized_email ?? "",
      phone: lead.normalized_phone ?? "",
      campaign: lead.campaign ?? "",
      specialty_id: lead.specialty_id ?? "",
      requested_service_id: lead.requested_service_id ?? "",
      branch_id: lead.branch_id ?? "",
      notes: lead.notes ?? "",
    });
    setEditing(true);
  }

  async function saveEdit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!lead) return;
    setBusy(true);
    try {
      const body: Record<string, unknown> = { expected_version: lead.version };
      if (edit.full_name !== lead.full_name) body.full_name = edit.full_name;
      if ((edit.email || null) !== lead.normalized_email) body.email = edit.email || null;
      if ((edit.phone || null) !== lead.normalized_phone) body.phone = edit.phone || null;
      if ((edit.campaign || null) !== lead.campaign) body.campaign = edit.campaign || null;
      if ((edit.specialty_id || null) !== lead.specialty_id) body.specialty_id = edit.specialty_id || null;
      if ((edit.requested_service_id || null) !== lead.requested_service_id) body.requested_service_id = edit.requested_service_id || null;
      if ((edit.branch_id || null) !== lead.branch_id) body.branch_id = edit.branch_id || null;
      if ((edit.notes || null) !== lead.notes) body.notes = edit.notes || null;
      if (Object.keys(body).length === 1) { toast.error("No changes to save."); setBusy(false); return; }
      await patch(`/api/v1/leads/${leadId}`, body);
      toast.success("Lead details updated.");
      setEditing(false);
      await loadLead();
    } catch (reason) { toast.error(errorMessage(reason, "The lead could not be updated.")); }
    finally { setBusy(false); }
  }

  async function convertToPatient() {
    if (!lead) return;
    const yes = await confirm({ message: `Convert "${lead.full_name}" to a patient? This links the lead to a new patient record.` });
    if (!yes) return;
    setBusy(true);
    try {
      const result = await post<{ patient_id?: string }>(`/api/v1/leads/${leadId}/convert`, {});
      toast.success("Lead converted to patient.");
      await loadLead();
      if (result?.patient_id) router.push(`/patients/${result.patient_id}`);
    } catch (reason) { toast.error(errorMessage(reason, "The lead could not be converted.")); }
    finally { setBusy(false); }
  }

  async function addActivity(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setActBusy(true);
    try {
      const body: Record<string, unknown> = { kind: actKind, body: actBody };
      if (actKind === "follow_up") body.due_at = actDueAt ? new Date(actDueAt).toISOString() : null;
      await post(`/api/v1/leads/${leadId}/activities`, body);
      setActBody("");
      setActDueAt("");
      toast.success("Activity logged.");
      await loadActivities();
    } catch (reason) { toast.error(errorMessage(reason, "The activity could not be added.")); }
    finally { setActBusy(false); }
  }

  const isTerminal = lead?.status === "converted" || lead?.status === "lost";

  return (
    <main className="dash-content lead-detail-content" aria-busy={loading}>
      <Link className="back-link" href="/leads">← Lead pipeline</Link>

      {error && (
        <div className="workspace-alert" role="alert">
          <strong>{error}</strong>
          <button className="ghost-button" type="button" onClick={() => void loadLead()}>Try again <span>→</span></button>
        </div>
      )}

      {loading && (
        <div className="dashboard-empty" role="status">
          <strong>Loading lead record</strong>
          <span>Checking your authorized scope…</span>
        </div>
      )}

      {!loading && lead && (
        <>
          {/* Hero */}
          <div className="lead-hero">
            <div className="lead-avatar-large">{lead.full_name.slice(0, 1).toUpperCase()}</div>
            <div>
              <p className="eyebrow">LEAD · {lead.source.toUpperCase()}</p>
              <h1>{lead.full_name}</h1>
              <p className="lead-meta">
                <span className={`pipeline-status status-${lead.status}`}>{statusLabel(lead.status)}</span>
                {lead.specialty_id && <span> · {specialtyNames.get(lead.specialty_id) ?? "Specialty"}</span>}
                {lead.branch_id && <span> · {branchNames.get(lead.branch_id) ?? "Branch"}</span>}
                {lead.campaign && <span> · {lead.campaign}</span>}
              </p>
            </div>
            <div className="lead-hero-actions">
              <button className="button button-secondary" type="button" onClick={() => { void loadLead(); void loadActivities(); }}>Refresh <span>↻</span></button>
              {!isTerminal && can("lead.manage") && (
                <button className="button button-secondary" type="button" onClick={openEdit} disabled={busy}>Edit details <span>✎</span></button>
              )}
              {!isTerminal && can("lead.manage") && (
                <button className="button button-primary" type="button" onClick={() => void convertToPatient()} disabled={busy}>Convert to patient <span>→</span></button>
              )}
              {lead.status !== "converted" && can("lead.manage") && (
                <button className="button button-secondary" type="button" onClick={() => void archiveLead()} disabled={busy}>Archive</button>
              )}
              {lead.converted_to_patient_id && (
                <Link className="button button-primary" href={`/patients/${lead.converted_to_patient_id}`}>Open patient <span>↗</span></Link>
              )}
            </div>
          </div>

          {editing && (
            <form className="surface-card lead-form" onSubmit={(e) => void saveEdit(e)}>
              <div className="surface-card-heading"><div><p className="eyebrow">EDIT LEAD</p><h2>Update contact and routing.</h2></div></div>
              <div className="form-grid">
                <label>Full name *<input required value={edit.full_name} onChange={(e) => setEdit({ ...edit, full_name: e.target.value })} /></label>
                <label>Email<input type="email" value={edit.email} onChange={(e) => setEdit({ ...edit, email: e.target.value })} /></label>
                <label>Phone<input value={edit.phone} onChange={(e) => setEdit({ ...edit, phone: e.target.value })} /></label>
                <label>Campaign<input value={edit.campaign} onChange={(e) => setEdit({ ...edit, campaign: e.target.value })} /></label>
                <label>Specialty<select value={edit.specialty_id} onChange={(e) => setEdit({ ...edit, specialty_id: e.target.value })}><option value="">Not selected</option>{specialties.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
                <label>Requested service<select value={edit.requested_service_id} onChange={(e) => setEdit({ ...edit, requested_service_id: e.target.value })}><option value="">Not selected</option>{services.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
                <label>Branch<select value={edit.branch_id} onChange={(e) => setEdit({ ...edit, branch_id: e.target.value })}><option value="">Unassigned</option>{branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</select></label>
                <label style={{ gridColumn: "1 / -1" }}>Notes<textarea value={edit.notes} onChange={(e) => setEdit({ ...edit, notes: e.target.value })} rows={2} style={{ width: "100%", resize: "vertical" }} /></label>
              </div>
              <div className="form-actions">
                <button className="button button-secondary" type="button" onClick={() => setEditing(false)}>Cancel</button>
                <button className="button button-primary" type="submit" disabled={busy}>{busy ? "Saving…" : "Save changes"} <span>↗</span></button>
              </div>
            </form>
          )}

          <div className="lead-detail-grid">
            {/* Info card */}
            <section className="detail-card">
              <p className="eyebrow">CONTACT DETAILS</p>
              <h2>Lead info</h2>
              <dl>
                <div><dt>Email</dt><dd>{lead.normalized_email ?? "Not provided"}</dd></div>
                <div><dt>Phone</dt><dd>{lead.normalized_phone ?? "Not provided"}</dd></div>
                <div><dt>Source</dt><dd>{statusLabel(lead.source)}</dd></div>
                <div><dt>Branch</dt><dd>{lead.branch_id ? (branchNames.get(lead.branch_id) ?? "Branch") : "Unassigned"}</dd></div>
                <div><dt>Created</dt><dd>{formatDate(lead.created_at)}</dd></div>
                <div><dt>Last updated</dt><dd>{formatDate(lead.updated_at)}</dd></div>
                <div><dt>Version</dt><dd>{lead.version}</dd></div>
              </dl>
              {lead.notes && <p className="lead-notes">{lead.notes}</p>}
              {lead.lost_reason && <p className="lead-lost-reason">Lost reason: {lead.lost_reason}</p>}
            </section>

            {/* Stage management */}
            <section className="detail-card">
              <p className="eyebrow">PIPELINE STAGE</p>
              <h2>Progress</h2>
              {!isTerminal && can("lead.manage") ? (
                <div className="stage-pipeline">
                  {stages.filter((s) => !["converted", "lost"].includes(s)).map((stage) => (
                    <button
                      key={stage}
                      className={`stage-step ${lead.status === stage ? "active" : ""}`}
                      type="button"
                      onClick={() => void updateStatus(stage)}
                      disabled={busy || lead.status === stage}
                    >
                      {statusLabel(stage)}
                    </button>
                  ))}
                  <button
                    className="stage-step stage-lost"
                    type="button"
                    onClick={() => void updateStatus("lost")}
                    disabled={busy}
                  >
                    Mark lost
                  </button>
                </div>
              ) : (
                <div className="stage-pipeline">
                  {stages.map((stage) => (
                    <span key={stage} className={`stage-step ${lead.status === stage ? "active" : ""}`}>{statusLabel(stage)}</span>
                  ))}
                </div>
              )}
            </section>
          </div>

          {/* Activity timeline */}
          <section className="detail-card lead-timeline-card">
            <div className="card-heading">
              <div><p className="eyebrow">ACTIVITY LOG</p><h2>Timeline</h2></div>
              <span className="directory-count">{activities.length} entries</span>
            </div>

            {can("lead.manage") && (
              <form className="lead-activity-form" onSubmit={(e) => void addActivity(e)}>
                <div className="lead-activity-fields">
                  <label>Type
                    <select value={actKind} onChange={(e) => setActKind(e.target.value as ActivityKind)}>
                      {activityKinds.map((k) => <option key={k} value={k}>{statusLabel(k)}</option>)}
                    </select>
                  </label>
                  <label className="lead-activity-body">Detail
                    <input required value={actBody} onChange={(e) => setActBody(e.target.value)} placeholder="What happened or what's next" />
                  </label>
                  {actKind === "follow_up" && (
                    <label>Due
                      <input type="datetime-local" required value={actDueAt} onChange={(e) => setActDueAt(e.target.value)} />
                    </label>
                  )}
                  <button className="button button-primary" type="submit" disabled={actBusy}>{actBusy ? "Adding…" : "Add"} <span>↗</span></button>
                </div>
              </form>
            )}

            {activitiesLoading && activities.length === 0 && (
              <div className="dashboard-empty" role="status"><strong>Loading timeline…</strong></div>
            )}
            {!activitiesLoading && activities.length === 0 && (
              <div className="dashboard-empty"><strong>No activity yet</strong><span>Log a call, note, message, or follow-up to start the timeline.</span></div>
            )}
            {activities.length > 0 && (
              <ol className="activity-list">
                {activities.map((a) => (
                  <li className="activity-item" key={a.id}>
                    <span className={`activity-kind kind-${a.kind}`}>{statusLabel(a.kind)}</span>
                    <div className="activity-body">
                      <p>{a.body}</p>
                      <small>{formatDateTime(a.created_at)}{a.due_at ? ` · due ${formatDateTime(a.due_at)}` : ""}</small>
                    </div>
                  </li>
                ))}
              </ol>
            )}
            {activitiesCursor && (
              <button className="button button-secondary" type="button" onClick={() => void loadActivities(activitiesCursor, true)} disabled={activitiesLoading}>
                {activitiesLoading ? "Loading…" : "Load more activity"} <span>↓</span>
              </button>
            )}
          </section>
        </>
      )}
    </main>
  );
}
