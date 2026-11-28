"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
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
type Consent = { id: string; consent_type: string; status: string; version: number; recorded_at: string };
type Media = { id: string; media_kind: string; captured_on: string | null; scan_status: string; approval_status: string; approved_for_website: boolean; version: number };
type Session = { permissions?: string[] };

const TABS = ["plans", "prescriptions", "forms", "tools", "consent"] as const;
type Tab = (typeof TABS)[number];
const list = <T,>(value: unknown): T[] => (Array.isArray(value) ? (value as T[]) : []);

const CONSENT_TYPES = [
  { value: "website_media", label: "Website media (before / after photos)" },
  { value: "treatment", label: "Treatment consent" },
  { value: "photography", label: "Clinical photography" },
  { value: "data_sharing", label: "Data sharing" },
];

const planStatusTone = (status: string) => status === "completed" ? "paid" : status === "cancelled" ? "void" : status === "active" ? "paid" : "contacted";
const stepStatusTone = (status: string) => status === "completed" ? "paid" : status === "cancelled" || status === "skipped" ? "void" : "contacted";

export default function ClinicalPage() {
  const { success: toastSuccess, error: toastError } = useToast();
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
        rows.sort((a, b) => a.full_name.localeCompare(b.full_name));
        setPatients(rows);
        if (rows[0]) { setPatientId(rows[0].id); await loadPatient(rows[0].id, granted); }
      } catch (reason) { toastError(errorMessage(reason, "Clinical records could not be loaded.")); }
      finally { setLoading(false); }
    })();
  }, [loadPatient, toastError]);

  const run = async (action: () => Promise<unknown>, success: string) => {
    setBusy(true);
    try { await action(); toastSuccess(success); await loadPatient(patientId, permissions); } catch (reason) { toastError(errorMessage(reason, "That change could not be saved.")); } finally { setBusy(false); }
  };
  const choosePatient = (id: string) => { setPatientId(id); setPlans([]); setPrescriptions([]); setConsents([]); setMedia([]); setMediaCursor(null); void loadPatient(id, permissions).catch((reason) => toastError(errorMessage(reason, "Records could not be loaded."))); };
  const loadMoreMedia = useCallback(async () => {
    if (!mediaCursor) return;
    try {
      const page = await apiPage<Media>(`/api/v1/patients/${patientId}/media?cursor=${encodeURIComponent(mediaCursor)}`);
      setMedia((current) => [...current, ...page.data]); setMediaCursor(page.nextCursor);
    } catch (reason) { toastError(errorMessage(reason, "More media could not be loaded.")); }
  }, [mediaCursor, patientId, toastError]);
  const notifyError = useCallback((message: string) => toastError(message), [toastError]);
  const text = (event: FormEvent<HTMLFormElement>, key: string) => String(new FormData(event.currentTarget).get(key) ?? "").trim();

  const addPlan = (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const target = event.currentTarget; const title = text(event, "title"); const diagnosis = text(event, "diagnosis"); void run(async () => { await post("/api/v1/treatment-plans", { patient_id: patientId, title, diagnosis: diagnosis || null }); target.reset(); }, "Treatment plan created."); };
  const addItem = (event: FormEvent<HTMLFormElement>, plan: Plan) => { event.preventDefault(); const target = event.currentTarget; const title = text(event, "title"); void run(async () => { await post(`/api/v1/treatment-plans/${plan.id}/items`, { title, sort_order: (items[plan.id]?.length ?? 0) }); target.reset(); }, "Item added."); };

  const cancelItem = async (plan: Plan, item: PlanItem) => {
    const yes = await confirm({ message: `Cancel "${item.title}"? This marks the step as skipped.`, danger: true });
    if (!yes) return;
    void run(() => patch(`/api/v1/treatment-plans/${plan.id}/items/${item.id}`, { expected_version: item.version, status: "skipped" }), "Item skipped.");
  };

  const addRx = (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const target = event.currentTarget; const body = { medication_name: text(event, "medication"), dosage: text(event, "dosage") || null, frequency: text(event, "frequency") || null, duration: text(event, "duration") || null }; void run(async () => { await post(`/api/v1/patients/${patientId}/prescriptions`, body); target.reset(); }, "Prescription recorded."); };
  const addConsent = (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const target = event.currentTarget; const consentType = text(event, "type"); void run(async () => { await post(`/api/v1/patients/${patientId}/consents`, { consent_type: consentType, status: "granted", version: "1" }); target.reset(); }, "Consent recorded."); };
  const grantedConsent = consents.find((item) => item.status === "granted" && item.consent_type === "website_media");
  const selectedPatient = patients.find((p) => p.id === patientId);
  const activePlans = plans.filter((p) => p.status === "active").length;

  return (
    <main className="dash-content clinical-content" aria-busy={loading}>
      <div className="dash-topline clinical-topline">
        <div>
          <p className="eyebrow">CLINICAL · CARE RECORDS</p>
          <h1>The treatment, <em>in one place.</em></h1>
          <p className="workspace-page-intro">Treatment plans, prescriptions, consent and patient media. Media only reaches your website after explicit consent and approval.</p>
        </div>
        <label className="clinical-patient-picker">
          <span className="eyebrow">PATIENT</span>
          <select value={patientId} onChange={(e) => choosePatient(e.target.value)}>
            {patients.length === 0 && <option value="">No patients</option>}
            {patients.map((p) => <option key={p.id} value={p.id}>{p.full_name} · {p.patient_number}</option>)}
          </select>
          {selectedPatient && <small>Records below belong to {selectedPatient.full_name}.</small>}
        </label>
      </div>

      <div className="pipeline-toolbar clinical-tabs">
        <div className="pipeline-tabs" role="tablist">
          {TABS.map((item) => <button key={item} role="tab" aria-selected={tab === item} className={tab === item ? "active" : ""} onClick={() => setTab(item)}>{item === "consent" ? "Consent & media" : label(item)}</button>)}
        </div>
        {!loading && <span className="clinical-tab-note">{plans.length} plan{plans.length === 1 ? "" : "s"} · {prescriptions.length} prescription{prescriptions.length === 1 ? "" : "s"} · {media.length} media</span>}
      </div>

      {tab === "plans" && (
        <section className="surface-card clinical-panel">
          <div className="surface-card-heading">
            <div><p className="eyebrow">TREATMENT PLANS</p><h2>What happens next.</h2>
              <p className="clinical-hint">Break the treatment into steps, then tick them off as the patient progresses.</p></div>
            {plans.length > 0 && <span className="clinical-count">{activePlans} active / {plans.length} total</span>}
          </div>
          {can("clinical.manage") && patientId && (
            <form className="drawer-form clinical-form" onSubmit={addPlan}>
              <div className="drawer-form-row drawer-form-row-2">
                <label><span className="clinical-field-label">Plan title <span className="drawer-note">required</span></span>
                  <input name="title" required maxLength={200} placeholder="Implant — lower left" /></label>
                <label><span className="clinical-field-label">Working diagnosis <span className="drawer-note">optional</span></span>
                  <input name="diagnosis" maxLength={500} placeholder="e.g. Missing 36, bone graft needed" /></label>
              </div>
              <div className="clinical-actions"><button className="button button-primary" type="submit" disabled={busy}>Create plan <span>→</span></button></div>
            </form>
          )}
          <div className="clinical-list">
            {plans.length === 0 && <div className="clinical-empty"><strong>No treatment plans</strong><span>Create the first plan above to start documenting steps.</span></div>}
            {plans.map((plan) => (
              <article className="clinical-plan" key={plan.id}>
                <div className="clinical-plan-head">
                  <div>
                    <h3>{plan.title}</h3>
                    <p>{plan.diagnosis ?? "No working diagnosis recorded"}</p>
                  </div>
                  <span className={`pipeline-status status-${planStatusTone(plan.status)}`}>{label(plan.status)}</span>
                </div>
                <ol className="clinical-steps">
                  {(items[plan.id] ?? []).map((item) => (
                    <li className={`clinical-step is-${item.status}`} key={item.id}>
                      <span className="clinical-step-dot" aria-hidden="true" />
                      <span className="clinical-step-title">{item.title}</span>
                      <span className={`pipeline-status status-${stepStatusTone(item.status)}`}>{label(item.status)}</span>
                      {can("clinical.manage") && item.status !== "completed" && item.status !== "cancelled" && item.status !== "skipped" && (
                        <span className="clinical-step-actions">
                          <button className="text-control" type="button" disabled={busy} onClick={() => void run(() => patch(`/api/v1/treatment-plans/${plan.id}/items/${item.id}`, { expected_version: item.version, status: "completed" }), "Item completed.")}>Done</button>
                          <button className="text-control danger-control" type="button" disabled={busy} onClick={() => void cancelItem(plan, item)}>Skip</button>
                        </span>
                      )}
                    </li>
                  ))}
                  {(items[plan.id] ?? []).length === 0 && <li className="clinical-step-empty">No steps yet — add the first one below.</li>}
                </ol>
                {can("clinical.manage") && (
                  <form className="clinical-add-step" onSubmit={(e) => addItem(e, plan)}>
                    <input name="title" required maxLength={200} placeholder="Add step, e.g. Crown fitting" aria-label={`New step for ${plan.title}`} />
                    <button className="button button-secondary" type="submit" disabled={busy}>Add step</button>
                  </form>
                )}
                {can("clinical.manage") && plan.status !== "completed" && plan.status !== "cancelled" && (
                  <div className="clinical-plan-actions">
                    <button className="text-control" type="button" disabled={busy} onClick={() => void run(() => patch(`/api/v1/treatment-plans/${plan.id}`, { expected_version: plan.version, status: plan.status === "draft" ? "active" : "completed" }), "Plan updated.")}>{plan.status === "draft" ? "Activate plan" : "Complete plan"}</button>
                    <button className="text-control danger-control" type="button" disabled={busy} onClick={async () => { const ok = await confirm({ message: `Cancel plan "${plan.title}"?`, danger: true }); if (ok) void run(() => patch(`/api/v1/treatment-plans/${plan.id}`, { expected_version: plan.version, status: "cancelled" }), "Plan cancelled."); }}>Cancel plan</button>
                  </div>
                )}
              </article>
            ))}
          </div>
        </section>
      )}

      {tab === "prescriptions" && (
        <section className="surface-card clinical-panel">
          <div className="surface-card-heading">
            <div><p className="eyebrow">PRESCRIPTIONS</p><h2>Medication instructions.</h2>
              <p className="clinical-hint">Record what the patient is taking; mark a course complete once it finishes.</p></div>
            {prescriptions.length > 0 && <span className="clinical-count">{prescriptions.length} recorded</span>}
          </div>
          {can("clinical.manage") && patientId && (
            <form className="drawer-form clinical-form" onSubmit={addRx}>
              <div className="drawer-form-row drawer-form-row-2">
                <label><span className="clinical-field-label">Medication <span className="drawer-note">required</span></span>
                  <input name="medication" required maxLength={200} placeholder="Amoxicillin" /></label>
                <label><span className="clinical-field-label">Dosage <span className="drawer-note">optional</span></span>
                  <input name="dosage" maxLength={200} placeholder="500 mg" /></label>
              </div>
              <div className="drawer-form-row drawer-form-row-2">
                <label><span className="clinical-field-label">Frequency <span className="drawer-note">optional</span></span>
                  <input name="frequency" maxLength={200} placeholder="Twice daily" /></label>
                <label><span className="clinical-field-label">Duration <span className="drawer-note">optional</span></span>
                  <input name="duration" maxLength={200} placeholder="7 days" /></label>
              </div>
              <div className="clinical-actions"><button className="button button-primary" type="submit" disabled={busy}>Record prescription <span>→</span></button></div>
            </form>
          )}
          <div className="clinical-list">
            {prescriptions.length === 0 && <div className="clinical-empty"><strong>No prescriptions</strong><span>Medication instructions you record appear here.</span></div>}
            {prescriptions.map((rx) => (
              <article className="clinical-row" key={rx.id}>
                <div className="clinical-row-mark">Rx</div>
                <div className="clinical-row-main">
                  <h3>{rx.medication_name}</h3>
                  <p>{[rx.dosage, rx.frequency, rx.duration].filter(Boolean).join(" · ") || "No dosage details"}</p>
                  <small>Prescribed {new Date(rx.prescribed_at).toLocaleDateString()}</small>
                </div>
                <div className="clinical-row-actions">
                  <span className={`pipeline-status status-${rx.status === "active" ? "contacted" : "paid"}`}>{label(rx.status)}</span>
                  {can("clinical.manage") && rx.status === "active" && (
                    <button className="text-control" type="button" disabled={busy} onClick={() => void run(() => patch(`/api/v1/patients/${patientId}/prescriptions/${rx.id}/status`, { expected_version: rx.version, status: "completed" }), "Prescription completed.")}>Complete</button>
                  )}
                </div>
              </article>
            ))}
          </div>
        </section>
      )}

      {tab === "forms" && <FormsPanel patientId={patientId} permissions={permissions} onError={notifyError} />}
      {tab === "tools" && <ToolsPanel patientId={patientId} permissions={permissions} onError={notifyError} />}

      {tab === "consent" && (
        <div className="clinical-stack">
          <section className="surface-card clinical-panel">
            <div className="surface-card-heading">
              <div><p className="eyebrow">CONSENT</p><h2>Nothing public without consent.</h2>
                <p className="clinical-hint">A granted <strong>website media</strong> consent is required before any photo can be approved for the website.</p></div>
              {grantedConsent
                ? <span className="pipeline-status status-paid">Website media consent granted</span>
                : <span className="pipeline-status status-contacted">Website media consent missing</span>}
            </div>
            {can("consent.manage") && patientId && (
              <form className="drawer-form clinical-form clinical-form-compact" onSubmit={addConsent}>
                <label><span className="clinical-field-label">Consent type <span className="drawer-note">required</span></span>
                  <select name="type" defaultValue="website_media" required>
                    {CONSENT_TYPES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
                  </select>
                </label>
                <div className="clinical-actions"><button className="button button-secondary" type="submit" disabled={busy}>Record granted consent <span>→</span></button></div>
              </form>
            )}
            <div className="clinical-list">
              {consents.length === 0 && <div className="clinical-empty"><strong>No consents recorded</strong><span>Record the patient&apos;s consent before uploading or publishing media.</span></div>}
              {consents.map((consent) => (
                <article className="clinical-row" key={consent.id}>
                  <div className="clinical-row-mark">✓</div>
                  <div className="clinical-row-main">
                    <h3>{CONSENT_TYPES.find((c) => c.value === consent.consent_type)?.label ?? consent.consent_type.replaceAll("_", " ")}</h3>
                    <small>Recorded {new Date(consent.recorded_at).toLocaleString()}</small>
                  </div>
                  <div className="clinical-row-actions">
                    <span className={`pipeline-status status-${consent.status === "granted" ? "paid" : "void"}`}>{label(consent.status)}</span>
                    {consent.status === "granted" && can("consent.manage") && <button className="text-control danger-control" type="button" disabled={busy} onClick={() => void run(() => post(`/api/v1/patients/${patientId}/consents/${consent.id}/revoke`, { expected_version: consent.version }), "Consent withdrawn.")}>Withdraw</button>}
                  </div>
                </article>
              ))}
            </div>
          </section>

          <section className="surface-card clinical-panel">
            <div className="surface-card-heading">
              <div><p className="eyebrow">PATIENT MEDIA</p><h2>Photos, reviewed before publishing.</h2>
                <p className="clinical-hint">Uploads are scanned first. Only clean, consented photos can be approved for the website.</p></div>
              {media.length > 0 && <span className="clinical-count">{media.length} uploaded</span>}
            </div>
            {can("patient.media.write") && patientId && <MediaUpload patientId={patientId} onUploaded={() => void run(() => Promise.resolve(), "Upload complete — scanning.")} />}
            {!grantedConsent && <p className="media-gate">Website approval is locked until a granted <strong>website media</strong> consent is recorded above.</p>}
            <div className="clinical-list">
              {media.length === 0 && <div className="clinical-empty"><strong>No patient media</strong><span>Uploaded before/after photos appear here for review.</span></div>}
              {media.map((item) => (
                <article className="clinical-row" key={item.id}>
                  <div className="clinical-row-mark">{item.media_kind.slice(0, 3).toUpperCase()}</div>
                  <div className="clinical-row-main">
                    <h3>{label(item.media_kind)} photo</h3>
                    <div className="media-tags">
                      <span className={`media-tag media-tag-${item.scan_status === "clean" ? "ok" : item.scan_status === "pending_scan" ? "wait" : "warn"}`}>Scan: {item.scan_status === "pending_scan" ? "scanning" : label(item.scan_status)}</span>
                      <span className={`media-tag media-tag-${item.approval_status === "approved" ? "ok" : item.approval_status === "revoked" ? "warn" : "wait"}`}>Approval: {label(item.approval_status)}</span>
                    </div>
                    <small>{item.captured_on ?? "No capture date"}{item.approved_for_website ? " · on website" : ""}</small>
                  </div>
                  <div className="clinical-row-actions">
                    {can("patient.media.write") && item.approval_status !== "approved" && (
                      <button className="text-control" type="button" disabled={busy || !grantedConsent || item.scan_status !== "clean"} title={!grantedConsent ? "Record a granted website media consent first" : item.scan_status !== "clean" ? "Photo must pass the scan first" : undefined} onClick={() => grantedConsent && void run(() => post(`/api/v1/patients/${patientId}/media/${item.id}/approve`, { expected_version: item.version, consent_record_id: grantedConsent.id }), "Approved for website.")}>Approve for website</button>
                    )}
                    {can("patient.media.write") && item.approval_status === "approved" && (
                      <button className="text-control" type="button" disabled={busy} onClick={() => void run(() => post(`/api/v1/patients/${patientId}/media/${item.id}/revoke`, { expected_version: item.version }), "Approval revoked.")}>Revoke</button>
                    )}
                  </div>
                </article>
              ))}
            </div>
            {mediaCursor && <button className="button button-secondary" type="button" disabled={busy} onClick={() => void loadMoreMedia()}>Load more media</button>}
          </section>
        </div>
      )}
    </main>
  );
}
