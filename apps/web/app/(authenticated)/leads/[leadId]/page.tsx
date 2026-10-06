"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { api, apiPage, post, patch, csrfToken, errorMessage } from "../../_lib/client";
import { useToast } from "../../_lib/toast";
import { useConfirm } from "../../_lib/confirm";

type Lead = { id: string; full_name: string; normalized_email: string | null; normalized_phone: string | null; source: string; campaign: string | null; status: string; specialty_id: string | null; assigned_to_user_id: string | null; converted_to_patient_id: string | null; lost_reason: string | null; notes: string | null; created_at: string; updated_at: string; version: number };
type Activity = { id: string; lead_id: string; actor_user_id: string; kind: string; body: string; due_at: string | null; created_at: string };
type Specialty = { id: string; name: string };
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
  const [permissions, setPermissions] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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

  const loadLead = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [session, leadData, specialtyData] = await Promise.all([
        api<Session>("/api/v1/auth/me"),
        api<Lead>(`/api/v1/leads/${leadId}`),
        api<Specialty[]>("/api/v1/specialties"),
      ]);
      setPermissions(session.permissions ?? []);
      setLead(leadData);
      setSpecialties(specialtyData ?? []);
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
    <section className="dash-content lead-detail-content" aria-busy={loading}>
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
                {lead.campaign && <span> · {lead.campaign}</span>}
              </p>
            </div>
            <div className="lead-hero-actions">
              <button className="button button-secondary" type="button" onClick={() => { void loadLead(); void loadActivities(); }}>Refresh <span>↻</span></button>
              {!isTerminal && can("lead.manage") && (
                <button className="button button-primary" type="button" onClick={() => void convertToPatient()} disabled={busy}>Convert to patient <span>→</span></button>
              )}
              {lead.converted_to_patient_id && (
                <Link className="button button-primary" href={`/patients/${lead.converted_to_patient_id}`}>Open patient <span>↗</span></Link>
              )}
            </div>
          </div>

          <div className="lead-detail-grid">
            {/* Info card */}
            <section className="detail-card">
              <p className="eyebrow">CONTACT DETAILS</p>
              <h2>Lead info</h2>
              <dl>
                <div><dt>Email</dt><dd>{lead.normalized_email ?? "Not provided"}</dd></div>
                <div><dt>Phone</dt><dd>{lead.normalized_phone ?? "Not provided"}</dd></div>
                <div><dt>Source</dt><dd>{statusLabel(lead.source)}</dd></div>
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
    </section>
  );
}
