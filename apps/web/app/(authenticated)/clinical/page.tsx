"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import anime from "animejs";
import { api, apiPage, errorMessage, label, patch, post } from "../_lib/client";
import { useToast } from "../_lib/toast";
import { useConfirm } from "../_lib/confirm";
import FormsPanel from "./forms-panel";
import MediaUpload from "./media-upload";
import ToolsPanel from "./tools-panel";

type Patient = { id: string; full_name: string; patient_number: string };
type Plan = { id: string; title: string; diagnosis: string | null; status: string; starts_on: string | null; version: number };
type PlanItem = { id: string; title: string; instructions: string | null; status: string; due_on: string | null; version: number };
type Prescription = { id: string; medication_name: string; dosage: string | null; frequency: string | null; duration: string | null; status: string; version: number; prescribed_at: string };
type Consent = { id: string; consent_type: string; status: string; recorded_at: string };
type Media = { id: string; media_kind: string; captured_on: string | null; scan_status: string; approval_status: string; approved_for_website: boolean; version: number };
type Session = { permissions?: string[] };

const TABS = ["plans", "prescriptions", "forms", "tools", "consent"] as const;
type Tab = (typeof TABS)[number];
const list = <T,>(value: unknown): T[] => (Array.isArray(value) ? (value as T[]) : []);

export default function ClinicalPage() {
  const toast = useToast();
  const confirm = useConfirm();
  const [permissions, setPermissions] = useState<string[]>([]);
  const [patients, setPatients] = useState<Patient[]>([]);
  const [patientId, setPatientId] = useState("");
  const [tab, setTab] = useState<Tab>("plans");
  const [plans, setPlans] = useState<Plan[]>([]);
  const [items, setItems] = useState<Record<string, PlanItem[]>>({});
  const [prescriptions, setPrescriptions] = useState<Prescription[]>([]);
  const [consents, setConsents] = useState<Consent[]>([]);
  const [media, setMedia] = useState<Media[]>([]);
  const [mediaCursor, setMediaCursor] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const can = (permission: string) => permissions.includes(permission);

  const loadPatient = useCallback(async (id: string, granted: string[]) => {
    if (!id) return;
    const has = (code: string) => granted.includes(code);
    const [planRows, prescriptionRows, consentRows, mediaRows] = await Promise.all([
      has("clinical.read") ? api<Plan[]>(`/api/v1/treatment-plans?patient_id=${id}&limit=50`).catch(() => []) : Promise.resolve([]),
      has("clinical.read") ? api<Prescription[]>(`/api/v1/patients/${id}/prescriptions`).catch(() => []) : Promise.resolve([]),
      has("consent.read") ? api<Consent[]>(`/api/v1/patients/${id}/consents`).catch(() => []) : Promise.resolve([]),
      has("patient.media.read") ? apiPage<Media>(`/api/v1/patients/${id}/media`).catch(() => ({ data: [], nextCursor: null })) : Promise.resolve({ data: [], nextCursor: null }),
    ]);
    const nextPlans = list<Plan>(planRows);
    setPlans(nextPlans); setPrescriptions(list<Prescription>(prescriptionRows)); setConsents(list<Consent>(consentRows)); setMedia(mediaRows.data); setMediaCursor(mediaRows.nextCursor);
    const entries = await Promise.all(nextPlans.map(async (plan) => [plan.id, list<PlanItem>(await api<PlanItem[]>(`/api/v1/treatment-plans/${plan.id}/items`).catch(() => []))] as const));
    setItems(Object.fromEntries(entries));
  }, []);

  useEffect(() => {
    void (async () => {
      try {
        setLoading(true);
        const session = await api<Session>("/api/v1/auth/me");
        const granted = session.permissions ?? [];
        setPermissions(granted);
        const rows = list<Patient>(await api<Patient[]>("/api/v1/patients?limit=100"));
        setPatients(rows);
        if (rows[0]) { setPatientId(rows[0].id); await loadPatient(rows[0].id, granted); }
      } catch (reason) { toast.error(errorMessage(reason, "Clinical records could not be loaded.")); }
      finally { setLoading(false); }
    })();
  }, [loadPatient, toast]);

  const run = async (action: () => Promise<unknown>, success: string) => {
    setBusy(true);
    try { await action(); toast.success(success); await loadPatient(patientId, permissions); } catch (reason) { toast.error(errorMessage(reason, "That change could not be saved.")); } finally { setBusy(false); }
  };
  const choosePatient = (id: string) => { setPatientId(id); setPlans([]); setPrescriptions([]); setConsents([]); setMedia([]); setMediaCursor(null); void loadPatient(id, permissions).catch((reason) => toast.error(errorMessage(reason, "Records could not be loaded."))); };
  const loadMoreMedia = useCallback(async () => {
    if (!mediaCursor) return;
    try {
      const page = await apiPage<Media>(`/api/v1/patients/${patientId}/media?cursor=${encodeURIComponent(mediaCursor)}`);
      setMedia((current) => [...current, ...page.data]); setMediaCursor(page.nextCursor);
    } catch (reason) { toast.error(errorMessage(reason, "More media could not be loaded.")); }
  }, [mediaCursor, patientId, toast]);
  const text = (event: FormEvent<HTMLFormElement>, key: string) => String(new FormData(event.currentTarget).get(key) ?? "").trim();

  const addPlan = (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const target = event.currentTarget; const title = text(event, "title"); const diagnosis = text(event, "diagnosis"); void run(async () => { await post("/api/v1/treatment-plans", { patient_id: patientId, title, diagnosis: diagnosis || null }); target.reset(); }, "Treatment plan created."); };
  const addItem = (event: FormEvent<HTMLFormElement>, plan: Plan) => { event.preventDefault(); const target = event.currentTarget; const title = text(event, "title"); void run(async () => { await post(`/api/v1/treatment-plans/${plan.id}/items`, { title, sort_order: (items[plan.id]?.length ?? 0) }); target.reset(); }, "Item added."); };

  const cancelItem = async (plan: Plan, item: PlanItem) => {
    const yes = await confirm({ message: `Cancel "${item.title}"? This marks the step as skipped.`, danger: true });
    if (!yes) return;
    void run(() => patch(`/api/v1/treatment-plans/${plan.id}/items/${item.id}`, { expected_version: item.version, status: "cancelled" }), "Item cancelled.");
  };

  const addRx = (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const target = event.currentTarget; const body = { medication_name: text(event, "medication"), dosage: text(event, "dosage") || null, frequency: text(event, "frequency") || null, duration: text(event, "duration") || null }; void run(async () => { await post(`/api/v1/patients/${patientId}/prescriptions`, body); target.reset(); }, "Prescription recorded."); };
  const addConsent = (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const target = event.currentTarget; const consentType = text(event, "type"); void run(async () => { await post(`/api/v1/patients/${patientId}/consents`, { consent_type: consentType, status: "granted", version: "1" }); target.reset(); }, "Consent recorded."); };
  const grantedConsent = consents.find((item) => item.status === "granted");

  const sectionRef = useRef<HTMLElement>(null);
  useEffect(() => {
    if (loading || !sectionRef.current) return;
    anime({
      targets: sectionRef.current.querySelectorAll(".surface-card, .panel-card, .clinical-tab-content"),
      opacity: [0, 1],
      translateY: [22, 0],
      duration: 500,
      delay: anime.stagger(60, { start: 150 }),
      easing: "easeOutCubic",
    });
  }, [loading, tab, patientId]);

  return (
    <section className="dash-content clinical-content" ref={sectionRef} aria-busy={loading}>
      <div className="dash-topline">
        <div>
          <p className="eyebrow">CLINICAL · CARE RECORDS</p>
          <h1>The treatment, <em>in one place.</em></h1>
          <p className="workspace-page-intro">Treatment plans, prescriptions, consent and patient media. Media only reaches your website after explicit consent and approval.</p>
        </div>
        <div className="header-actions">
          <label className="report-period">Patient
            <select value={patientId} onChange={(e) => choosePatient(e.target.value)}>
              {patients.length === 0 && <option value="">No patients</option>}
              {patients.map((p) => <option key={p.id} value={p.id}>{p.full_name} · {p.patient_number}</option>)}
            </select>
          </label>
        </div>
      </div>

      <div className="pipeline-toolbar">
        <div className="pipeline-tabs" role="tablist">
          {TABS.map((item) => <button key={item} role="tab" aria-selected={tab === item} className={tab === item ? "active" : ""} onClick={() => setTab(item)}>{item === "consent" ? "Consent & media" : label(item)}</button>)}
        </div>
      </div>

      {tab === "plans" && (
        <section className="surface-card">
          <div className="surface-card-heading"><div><p className="eyebrow">TREATMENT PLANS</p><h2>What happens next.</h2></div></div>
          {can("clinical.manage") && patientId && (
            <form className="manage-form" onSubmit={addPlan}>
              <div className="form-grid">
                <label>Title <input name="title" required maxLength={200} placeholder="Implant — lower left" /></label>
                <label>Diagnosis <span className="field-optional">optional</span> <input name="diagnosis" maxLength={500} /></label>
              </div>
              <div className="form-actions"><button className="button button-primary" type="submit" disabled={busy}>Create plan</button></div>
            </form>
          )}
          <div className="invoice-list">
            {plans.length === 0 && <div className="dashboard-empty"><strong>No treatment plans</strong></div>}
            {plans.map((plan) => (
              <article className="invoice-row" key={plan.id}>
                <div className="invoice-mark">PLN</div>
                <div className="invoice-main">
                  <h3>{plan.title}</h3>
                  <p>{plan.diagnosis ?? "No diagnosis recorded"}</p>
                  {(items[plan.id] ?? []).map((item) => (
                    <div className="theme-row" key={item.id}>
                      <span>{item.title}</span>
                      <span className={`pipeline-status status-${item.status === "completed" ? "paid" : item.status === "cancelled" ? "void" : "contacted"}`}>{label(item.status)}</span>
                      {can("clinical.manage") && item.status !== "completed" && item.status !== "cancelled" && (
                        <>
                          <button className="text-control" type="button" disabled={busy} onClick={() => void run(() => patch(`/api/v1/treatment-plans/${plan.id}/items/${item.id}`, { expected_version: item.version, status: "completed" }), "Item completed.")}>Done</button>
                          <button className="text-control" type="button" disabled={busy} onClick={() => void cancelItem(plan, item)}>Cancel</button>
                        </>
                      )}
                    </div>
                  ))}
                  {can("clinical.manage") && (
                    <form className="theme-row" onSubmit={(e) => addItem(e, plan)}>
                      <input name="title" required maxLength={200} placeholder="Add step, e.g. Crown fitting" aria-label={`New step for ${plan.title}`} />
                      <button className="text-control" type="submit" disabled={busy}>Add step</button>
                    </form>
                  )}
                </div>
                <div className="invoice-actions">
                  <span className={`pipeline-status status-${plan.status === "completed" ? "paid" : plan.status === "cancelled" ? "void" : "contacted"}`}>{plan.status}</span>
                  {can("clinical.manage") && plan.status !== "completed" && plan.status !== "cancelled" && (
                    <>
                      <button className="text-control" type="button" disabled={busy} onClick={() => void run(() => patch(`/api/v1/treatment-plans/${plan.id}`, { expected_version: plan.version, status: plan.status === "draft" ? "active" : "completed" }), "Plan updated.")}>{plan.status === "draft" ? "Activate" : "Complete"}</button>
                      <button className="text-control danger-control" type="button" disabled={busy} onClick={async () => { const ok = await confirm({ message: `Cancel plan "${plan.title}"?`, danger: true }); if (ok) void run(() => patch(`/api/v1/treatment-plans/${plan.id}`, { expected_version: plan.version, status: "cancelled" }), "Plan cancelled."); }}>Cancel</button>
                    </>
                  )}
                </div>
              </article>
            ))}
          </div>
        </section>
      )}

      {tab === "prescriptions" && (
        <section className="surface-card">
          <div className="surface-card-heading"><div><p className="eyebrow">PRESCRIPTIONS</p><h2>Medication instructions.</h2></div></div>
          {can("clinical.manage") && patientId && (
            <form className="manage-form" onSubmit={addRx}>
              <div className="form-grid">
                <label>Medication <input name="medication" required maxLength={200} /></label>
                <label>Dosage <input name="dosage" maxLength={200} placeholder="500 mg" /></label>
                <label>Frequency <input name="frequency" maxLength={200} placeholder="Twice daily" /></label>
                <label>Duration <input name="duration" maxLength={200} placeholder="7 days" /></label>
              </div>
              <div className="form-actions"><button className="button button-primary" type="submit" disabled={busy}>Record prescription</button></div>
            </form>
          )}
          <div className="invoice-list">
            {prescriptions.length === 0 && <div className="dashboard-empty"><strong>No prescriptions</strong></div>}
            {prescriptions.map((rx) => (
              <article className="invoice-row" key={rx.id}>
                <div className="invoice-mark">Rx</div>
                <div className="invoice-main">
                  <h3>{rx.medication_name}</h3>
                  <p>{[rx.dosage, rx.frequency, rx.duration].filter(Boolean).join(" · ") || "No details"}</p>
                  <small>{new Date(rx.prescribed_at).toLocaleDateString()}</small>
                </div>
                <div className="invoice-actions">
                  <span className={`pipeline-status status-${rx.status === "active" ? "contacted" : "paid"}`}>{rx.status}</span>
                  {can("clinical.manage") && rx.status === "active" && (
                    <button className="text-control" type="button" disabled={busy} onClick={() => void run(() => patch(`/api/v1/patients/${patientId}/prescriptions/${rx.id}/status`, { expected_version: rx.version, status: "completed" }), "Prescription completed.")}>Complete</button>
                  )}
                </div>
              </article>
            ))}
          </div>
        </section>
      )}

      {tab === "forms" && <FormsPanel patientId={patientId} permissions={permissions} onError={(msg) => toast.error(msg)} />}
      {tab === "tools" && <ToolsPanel patientId={patientId} permissions={permissions} onError={(msg) => toast.error(msg)} />}

      {tab === "consent" && (
        <section className="surface-card">
          <div className="surface-card-heading"><div><p className="eyebrow">CONSENT &amp; MEDIA</p><h2>Nothing public without consent.</h2></div></div>
          {can("consent.manage") && patientId && (
            <form className="manage-form" onSubmit={addConsent}>
              <div className="form-grid">
                <label>Consent type <input name="type" required maxLength={80} placeholder="website_media" /></label>
              </div>
              <div className="form-actions"><button className="button button-secondary" type="submit" disabled={busy}>Record granted consent</button></div>
            </form>
          )}
          <div className="invoice-list">
            {consents.map((consent) => (
              <article className="invoice-row" key={consent.id}>
                <div className="invoice-mark">✓</div>
                <div className="invoice-main"><h3>{consent.consent_type}</h3><small>{new Date(consent.recorded_at).toLocaleString()}</small></div>
                <div className="invoice-actions"><span className={`pipeline-status status-${consent.status === "granted" ? "paid" : "void"}`}>{consent.status}</span></div>
              </article>
            ))}
            {can("patient.media.write") && <MediaUpload patientId={patientId} onUploaded={() => void run(() => Promise.resolve(), "Upload complete — scanning.")} />}
            {media.length === 0 && <div className="dashboard-empty"><strong>No patient media</strong><span>Uploaded before/after photos appear here for review.</span></div>}
            {media.map((item) => (
              <article className="invoice-row" key={item.id}>
                <div className="invoice-mark">{item.media_kind.slice(0, 3).toUpperCase()}</div>
                <div className="invoice-main">
                  <h3>{label(item.media_kind)} photo</h3>
                  <p>Scan: {item.scan_status} · Approval: {item.approval_status}</p>
                  <small>{item.captured_on ?? "No capture date"}{item.approved_for_website ? " · on website" : ""}</small>
                </div>
                <div className="invoice-actions">
                  {can("patient.media.write") && item.approval_status !== "approved" && (
                    <button className="text-control" type="button" disabled={busy || !grantedConsent || item.scan_status !== "clean"} title={!grantedConsent ? "Record granted consent first" : undefined} onClick={() => grantedConsent && void run(() => post(`/api/v1/patients/${patientId}/media/${item.id}/approve`, { expected_version: item.version, consent_record_id: grantedConsent.id }), "Approved for website.")}>Approve for website</button>
                  )}
                  {can("patient.media.write") && item.approval_status === "approved" && (
                    <button className="text-control" type="button" disabled={busy} onClick={() => void run(() => post(`/api/v1/patients/${patientId}/media/${item.id}/revoke`, { expected_version: item.version }), "Approval revoked.")}>Revoke</button>
                  )}
                </div>
              </article>
            ))}
            {mediaCursor && <button className="button button-secondary" type="button" disabled={busy} onClick={() => void loadMoreMedia()}>Load more media</button>}
          </div>
        </section>
      )}
    </section>
  );
}
