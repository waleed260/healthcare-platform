"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import anime from "animejs";

type Lead = { id: string; full_name: string; normalized_email: string | null; normalized_phone: string | null; source: string; campaign: string | null; status: string; specialty_id: string | null; requested_service_id: string | null; assigned_to_user_id: string | null; converted_to_patient_id: string | null; lost_reason: string | null; notes: string | null; created_at: string; version: number };
type Specialty = { id: string; name: string; code: string };
type Service = { id: string; name: string };
type StaffUser = { user_id: string; display_name: string };
type Session = { permissions?: string[] };
type Activity = { id: string; lead_id: string; actor_user_id: string; kind: string; body: string; due_at: string | null; created_at: string };

const stages = ["new", "contacted", "qualified", "appointment_booked", "visited", "converted", "lost"];
const sources = ["website", "meta_ads", "google_ads", "instagram", "referral", "walk-in", "call", "import", "other"] as const;
const activityKinds = ["call", "note", "message", "follow_up"] as const;
type ActivityKind = (typeof activityKinds)[number];
const stageLabel = (value: string) => value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
const dateTime = (value: string) => new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }).format(new Date(value));
import { api, apiPage, errorMessage, writeHeaders } from "../_lib/client";

export default function LeadsPage() {
  const [leads, setLeads] = useState<Lead[]>([]); const [specialties, setSpecialties] = useState<Specialty[]>([]); const [services, setServices] = useState<Service[]>([]); const [staffUsers, setStaffUsers] = useState<StaffUser[]>([]); const [permissions, setPermissions] = useState<string[]>([]); const [filter, setFilter] = useState("all"); const [showForm, setShowForm] = useState(false); const [loading, setLoading] = useState(true); const [loadingMore, setLoadingMore] = useState(false); const [busy, setBusy] = useState<string | null>(null); const [error, setError] = useState<string | null>(null); const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [fullName, setFullName] = useState(""); const [email, setEmail] = useState(""); const [phone, setPhone] = useState(""); const [source, setSource] = useState("website"); const [specialtyId, setSpecialtyId] = useState(""); const [campaign, setCampaign] = useState(""); const [requestedServiceId, setRequestedServiceId] = useState(""); const [assignedToUserId, setAssignedToUserId] = useState(""); const [leadNotes, setLeadNotes] = useState("");
  const [lostLeadId, setLostLeadId] = useState<string | null>(null); const [lostReason, setLostReason] = useState("");
  // Inline lead-activity timeline (the feature this branch is named for).
  const [openLeadId, setOpenLeadId] = useState<string | null>(null); const [activities, setActivities] = useState<Activity[]>([]); const [activitiesCursor, setActivitiesCursor] = useState<string | null>(null); const [activitiesLoading, setActivitiesLoading] = useState(false); const [activityError, setActivityError] = useState<string | null>(null);
  const [actKind, setActKind] = useState<ActivityKind>("call"); const [actBody, setActBody] = useState(""); const [actDueAt, setActDueAt] = useState(""); const [actBusy, setActBusy] = useState(false);
  const can = (permission: string) => permissions.includes(permission);

  const loadLeads = useCallback(async (cursor: string | null = null, append = false) => {
    if (append) setLoadingMore(true); else setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ limit: "100" });
      if (filter !== "all") params.set("status", filter);
      if (cursor) params.set("cursor", cursor);
      const [session, page, specialtyRows, serviceRows, staffRows] = await Promise.all([
        append ? Promise.resolve<Session | null>(null) : api<Session>("/api/v1/auth/me"),
        apiPage<Lead>(`/api/v1/leads?${params.toString()}`),
        append ? Promise.resolve<Specialty[] | null>(null) : api<Specialty[]>("/api/v1/specialties"),
        append ? Promise.resolve<Service[] | null>(null) : api<Service[]>("/api/v1/services?limit=200").catch(() => null),
        append ? Promise.resolve<StaffUser[] | null>(null) : api<StaffUser[]>("/api/v1/staff/users?limit=200").catch(() => null),
      ]);
      if (session) setPermissions(session.permissions ?? []);
      if (specialtyRows) setSpecialties(specialtyRows ?? []);
      if (serviceRows) setServices(serviceRows ?? []);
      if (staffRows) setStaffUsers(staffRows ?? []);
      setLeads((current) => append ? [...current, ...page.data] : page.data);
      setNextCursor(page.nextCursor);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "The lead pipeline could not be loaded."); }
    finally { setLoading(false); setLoadingMore(false); }
  }, [filter]);
  useEffect(() => { setOpenLeadId(null); void loadLeads(); }, [loadLeads]);

  const specialtyNames = useMemo(() => new Map(specialties.map((item) => [item.id, item.name])), [specialties]);
  const serviceNames = useMemo(() => new Map(services.map((item) => [item.id, item.name])), [services]);
  const staffNames = useMemo(() => new Map(staffUsers.map((item) => [item.user_id, item.display_name])), [staffUsers]);

  const loadActivities = useCallback(async (leadId: string, cursor: string | null = null, append = false) => {
    setActivitiesLoading(true); setActivityError(null);
    try {
      const params = new URLSearchParams({ limit: "50" });
      if (cursor) params.set("cursor", cursor);
      const page = await apiPage<Activity>(`/api/v1/leads/${leadId}/activities?${params.toString()}`);
      setActivities((current) => append ? [...current, ...page.data] : page.data);
      setActivitiesCursor(page.nextCursor);
    } catch (reason) { setActivityError(reason instanceof Error ? reason.message : "The timeline could not be loaded."); }
    finally { setActivitiesLoading(false); }
  }, []);

  const toggleTimeline = (leadId: string) => {
    if (openLeadId === leadId) { setOpenLeadId(null); return; }
    setOpenLeadId(leadId); setActivities([]); setActivitiesCursor(null); setActivityError(null); setActKind("call"); setActBody(""); setActDueAt("");
    void loadActivities(leadId);
  };

  const addActivity = async (event: FormEvent<HTMLFormElement>, leadId: string) => {
    event.preventDefault(); setActBusy(true); setActivityError(null);
    try {
      const body: Record<string, unknown> = { kind: actKind, body: actBody };
      // The API requires a due date only for follow-ups and rejects it otherwise.
      if (actKind === "follow_up") body.due_at = actDueAt ? new Date(actDueAt).toISOString() : null;
      await api<Activity>(`/api/v1/leads/${leadId}/activities`, { method: "POST", headers: writeHeaders(), body: JSON.stringify(body) });
      setActBody(""); setActDueAt("");
      await loadActivities(leadId); // reload so the newest entry shows at the top in order
    } catch (reason) { setActivityError(reason instanceof Error ? reason.message : "The activity could not be added."); }
    finally { setActBusy(false); }
  };

  const createLead = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setBusy("create"); setError(null);
    try {
      await api<Lead>("/api/v1/leads", { method: "POST", headers: writeHeaders(), body: JSON.stringify({
        full_name: fullName, email: email || null, phone: phone || null, source,
        campaign: campaign || null, specialty_id: specialtyId || null,
        requested_service_id: requestedServiceId || null,
        assigned_to_user_id: assignedToUserId || null,
        notes: leadNotes || null,
      }) });
      setFullName(""); setEmail(""); setPhone(""); setCampaign(""); setRequestedServiceId(""); setAssignedToUserId(""); setLeadNotes(""); setShowForm(false);
      await loadLeads();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "The lead could not be created."); }
    finally { setBusy(null); }
  };
  const updateLead = async (lead: Lead, status: string) => { setBusy(lead.id); setError(null); try { await api(`/api/v1/leads/${lead.id}`, { method: "PATCH", headers: writeHeaders(), body: JSON.stringify({ expected_version: lead.version, status }) }); await loadLeads(); } catch (reason) { setError(reason instanceof Error ? reason.message : "The lead could not be updated."); } finally { setBusy(null); } };
  const markLost = async (lead: Lead) => {
    if (!lostReason.trim()) return;
    setBusy(lead.id); setError(null);
    try {
      await api(`/api/v1/leads/${lead.id}`, { method: "PATCH", headers: writeHeaders(), body: JSON.stringify({ expected_version: lead.version, status: "lost", lost_reason: lostReason.trim() }) });
      setLostLeadId(null); setLostReason(""); await loadLeads();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "The lead could not be marked as lost."); }
    finally { setBusy(null); }
  };
  const reopenLead = async (lead: Lead) => { setBusy(lead.id); setError(null); try { await api(`/api/v1/leads/${lead.id}`, { method: "PATCH", headers: writeHeaders(), body: JSON.stringify({ expected_version: lead.version, status: "new" }) }); await loadLeads(); } catch (reason) { setError(reason instanceof Error ? reason.message : "The lead could not be reopened."); } finally { setBusy(null); } };
  const convertLead = async (lead: Lead) => { setBusy(lead.id); setError(null); try { await api(`/api/v1/leads/${lead.id}/convert`, { method: "POST", headers: writeHeaders(), body: JSON.stringify({}) }); await loadLeads(); } catch (reason) { setError(reason instanceof Error ? reason.message : "The lead could not be converted."); } finally { setBusy(null); } };

  const leadListRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (loading || leads.length === 0 || !leadListRef.current) return;
    anime({
      targets: leadListRef.current.querySelectorAll(".lead-row"),
      opacity: [0, 1],
      translateY: [20, 0],
      duration: 450,
      delay: anime.stagger(40, { start: 100 }),
      easing: "easeOutCubic",
    });
  }, [loading, leads.length]);

  return <main className="workspace-page leads-page"><div className="workspace-page-header"><div><p className="eyebrow">CRM · DEMAND TO CARE</p><h1>Keep the <em>conversation</em> moving.</h1><p className="workspace-page-intro">Every enquiry has a next best action. Capture interest, keep ownership visible, and convert without duplicating the patient record.</p></div><div className="header-actions"><button className="button button-secondary" onClick={() => void loadLeads()} disabled={loading}>Refresh <span>↻</span></button>{can("lead.manage") && <button className="button button-primary" onClick={() => setShowForm((value) => !value)}>{showForm ? "Close form" : "New lead"} <span>＋</span></button>}</div></div>{error && <div className="workspace-alert" role="alert"><strong>{error}</strong><button className="ghost-button" onClick={() => void loadLeads()}>Try again <span>→</span></button></div>}<div className="pipeline-toolbar"><div className="pipeline-tabs" role="tablist" aria-label="Lead stages"><button className={filter === "all" ? "active" : ""} onClick={() => setFilter("all")}>All <b>{leads.length}{nextCursor ? "+" : ""}</b></button>{stages.map((stage) => <button key={stage} className={filter === stage ? "active" : ""} onClick={() => setFilter(stage)}>{stageLabel(stage)}</button>)}</div></div>{showForm && <form className="surface-card lead-form" onSubmit={createLead}><div className="surface-card-heading"><div><p className="eyebrow">NEW INTAKE</p><h2>Give the enquiry a clear owner.</h2></div><span className="accent-number">01</span></div><div className="form-grid">
  <label>Full name *<input required value={fullName} onChange={(event) => setFullName(event.target.value)} placeholder="Amina Rahman" /></label>
  <label>Email<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="amina@example.com" /></label>
  <label>Phone<input value={phone} onChange={(event) => setPhone(event.target.value)} placeholder="+92 300 0000000" /></label>
  <label>Source<select value={source} onChange={(event) => setSource(event.target.value)}>{sources.map((s) => <option key={s} value={s}>{stageLabel(s)}</option>)}</select></label>
  <label>Campaign / Ad<input value={campaign} onChange={(event) => setCampaign(event.target.value)} placeholder="e.g. FB-Oct-Promo" /></label>
  <label>Specialty<select value={specialtyId} onChange={(event) => setSpecialtyId(event.target.value)}><option value="">Not selected</option>{specialties.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
  <label>Requested service<select value={requestedServiceId} onChange={(event) => setRequestedServiceId(event.target.value)}><option value="">Not selected</option>{services.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
  <label>Assign to<select value={assignedToUserId} onChange={(event) => setAssignedToUserId(event.target.value)}><option value="">Unassigned</option>{staffUsers.map((item) => <option key={item.user_id} value={item.user_id}>{item.display_name}</option>)}</select></label>
  <label style={{ gridColumn: "1 / -1" }}>Notes<textarea value={leadNotes} onChange={(event) => setLeadNotes(event.target.value)} placeholder="Initial enquiry notes" rows={2} style={{ width: "100%", resize: "vertical" }} /></label>
</div><div className="form-actions"><button className="button button-primary" type="submit" disabled={busy === "create"}>{busy === "create" ? "Saving…" : "Add lead"} <span>↗</span></button></div></form>}<section className="surface-card pipeline-card"><div className="surface-card-heading"><div><p className="eyebrow">ACTIVE PIPELINE</p><h2>{filter === "all" ? "Every open conversation" : stageLabel(filter)}</h2></div><span className="muted-mono">{loading ? "SYNCING" : `${leads.length}${nextCursor ? "+" : ""} RECORD${leads.length === 1 ? "" : "S"} LOADED`}</span></div>{loading && <div className="dashboard-empty" role="status"><strong>Loading the pipeline</strong><span>Checking your authorized leads…</span></div>}{!loading && leads.length === 0 && <div className="dashboard-empty"><strong>No leads in this view</strong><span>New enquiries will appear here as soon as they arrive.</span></div>}{!loading && leads.length > 0 && <div className="lead-list" ref={leadListRef}>{leads.map((lead) => <article className={`lead-row${openLeadId === lead.id ? " lead-row-open" : ""}`} key={lead.id}><div className="lead-row-summary"><div className="lead-avatar">{lead.full_name.slice(0, 1).toUpperCase()}</div><div className="lead-main"><div className="lead-title"><h3><Link href={`/leads/${lead.id}`}>{lead.full_name}</Link></h3><span className={`pipeline-status status-${lead.status}`}>{stageLabel(lead.status)}</span></div><p>{lead.normalized_email ?? lead.normalized_phone ?? "No contact detail"} · {lead.source}{lead.campaign ? ` · ${lead.campaign}` : ""}{lead.specialty_id ? ` · ${specialtyNames.get(lead.specialty_id) ?? "Specialty"}` : ""}{lead.requested_service_id ? ` · ${serviceNames.get(lead.requested_service_id) ?? "Service"}` : ""}{lead.assigned_to_user_id ? ` · ${staffNames.get(lead.assigned_to_user_id) ?? "Assigned"}` : ""}</p><small>Added {new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(new Date(lead.created_at))}</small></div><div className="lead-actions"><button className="text-control" aria-expanded={openLeadId === lead.id} onClick={() => toggleTimeline(lead.id)}>{openLeadId === lead.id ? "Hide timeline" : "Timeline"} <span>{openLeadId === lead.id ? "▾" : "▸"}</span></button>{lead.status !== "converted" && lead.status !== "lost" && can("lead.manage") && <select aria-label={`Move ${lead.full_name}`} value={lead.status} onChange={(event) => void updateLead(lead, event.target.value)} disabled={busy === lead.id}>{stages.filter((stage) => !["converted", "lost"].includes(stage)).map((stage) => <option key={stage} value={stage}>{stageLabel(stage)}</option>)}</select>}{lead.status !== "converted" && lead.status !== "lost" && can("lead.manage") && <button className="text-control" onClick={() => void convertLead(lead)} disabled={busy === lead.id}>Convert to patient <span>→</span></button>}{lead.status !== "converted" && lead.status !== "lost" && can("lead.manage") && <button className="text-control danger-control" onClick={() => setLostLeadId(lostLeadId === lead.id ? null : lead.id)}>Mark lost</button>}{lead.status === "lost" && can("lead.manage") && <button className="text-control" onClick={() => void reopenLead(lead)} disabled={busy === lead.id}>Reopen <span>↺</span></button>}{lead.status === "lost" && lead.lost_reason && <small style={{ color: "var(--coral)", fontSize: 10 }}>Lost: {lead.lost_reason}</small>}{lead.converted_to_patient_id && <Link className="text-link" href={`/patients/${lead.converted_to_patient_id}`}>Open patient <span>↗</span></Link>}</div>{lostLeadId === lead.id && <div className="lead-lost-form" style={{ display: "flex", gap: 8, alignItems: "center", padding: "8px 0 0", marginTop: 4, borderTop: "1px solid var(--line)" }}><input style={{ flex: 1, fontSize: 12 }} value={lostReason} onChange={(e) => setLostReason(e.target.value)} placeholder="Reason for marking as lost" /><button className="button button-secondary" style={{ fontSize: 11, padding: "4px 12px" }} type="button" disabled={!lostReason.trim() || busy === lead.id} onClick={() => void markLost(lead)}>{busy === lead.id ? "Saving…" : "Confirm"}</button></div>}</div>{openLeadId === lead.id && <div className="lead-timeline" aria-label={`Activity timeline for ${lead.full_name}`}>{can("lead.manage") && <form className="lead-activity-form" onSubmit={(event) => void addActivity(event, lead.id)}><div className="lead-activity-fields"><label>Type<select value={actKind} onChange={(event) => setActKind(event.target.value as ActivityKind)}>{activityKinds.map((kind) => <option key={kind} value={kind}>{stageLabel(kind)}</option>)}</select></label><label className="lead-activity-body">Detail<input required value={actBody} onChange={(event) => setActBody(event.target.value)} placeholder="What happened or what's next" /></label>{actKind === "follow_up" && <label>Due<input type="datetime-local" required value={actDueAt} onChange={(event) => setActDueAt(event.target.value)} /></label>}<button className="button button-primary" type="submit" disabled={actBusy}>{actBusy ? "Adding…" : "Add"} <span>↗</span></button></div></form>}{activityError && <div className="workspace-alert" role="alert"><strong>{activityError}</strong></div>}{activitiesLoading && activities.length === 0 && <div className="dashboard-empty" role="status"><strong>Loading timeline…</strong></div>}{!activitiesLoading && activities.length === 0 && !activityError && <div className="dashboard-empty"><strong>No activity yet</strong><span>Log a call, note, message, or follow-up to start the timeline.</span></div>}{activities.length > 0 && <ol className="activity-list">{activities.map((activity) => <li className="activity-item" key={activity.id}><span className={`activity-kind kind-${activity.kind}`}>{stageLabel(activity.kind)}</span><div className="activity-body"><p>{activity.body}</p><small>{dateTime(activity.created_at)}{activity.due_at ? ` · due ${dateTime(activity.due_at)}` : ""}</small></div></li>)}</ol>}{activitiesCursor && <button className="button button-secondary" type="button" onClick={() => void loadActivities(lead.id, activitiesCursor, true)} disabled={activitiesLoading}>{activitiesLoading ? "Loading…" : "Load more activity"} <span>↓</span></button>}</div>}</article>)}</div>}{nextCursor && !loading && <button className="button button-secondary lead-load-more" type="button" onClick={() => void loadLeads(nextCursor, true)} disabled={loadingMore} aria-label="Load more leads">{loadingMore ? "Loading more…" : "Load more leads"} <span>↓</span></button>}</section></main>;
}
