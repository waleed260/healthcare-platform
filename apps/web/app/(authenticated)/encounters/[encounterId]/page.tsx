"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import anime from "animejs";
import { api, errorMessage, writeHeaders } from "../../_lib/client";
import { useToast } from "../../_lib/toast";
import { useConfirm } from "../../_lib/confirm";

type Vitals = { blood_pressure?: string; pulse?: number; temperature?: number; respiratory_rate?: number; oxygen_saturation?: number; weight_kg?: number; height_cm?: number; notes?: string };
type Medication = { name: string; dosage?: string; route?: string; frequency?: string; duration?: string; notes?: string };
type Encounter = {
  id: string; patient_id: string; patient_name: string; mrn: string | null;
  appointment_id: string | null; doctor_id: string; doctor_name: string;
  doctor_specialty: string | null; branch_id: string | null; branch_name: string | null;
  encounter_type: string; status: string;
  chief_complaint: string | null; history_present_illness: string | null;
  examination_findings: string | null; diagnosis: string | null;
  investigations: string | null; treatment_plan: string | null;
  medications: Medication[] | null; procedures_performed: string | null;
  follow_up_instructions: string | null; follow_up_date: string | null;
  arrival_vitals: Vitals | null; discharge_vitals: Vitals | null;
  discharge_notes: string | null; internal_notes: string | null;
  finalized_at: string | null; finalized_by: string | null;
  created_at: string; updated_at: string; version: number;
};

const fmtDate = (v: string) => new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(v));
const fmtDateTime = (v: string) => new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(v));
const typeLabel = (v: string) => v.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
const statusColor: Record<string, string> = { draft: "#e0a458", in_review: "var(--accent)", finalized: "var(--leaf)" };

export default function EncounterDetailPage() {
  const { encounterId } = useParams<{ encounterId: string }>();
  const toast = useToast();
  const confirm = useConfirm();

  const [enc, setEnc] = useState<Encounter | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<"assessment" | "medications" | "vitals" | "discharge">("assessment");

  const [complaint, setComplaint] = useState("");
  const [hpi, setHpi] = useState("");
  const [exam, setExam] = useState("");
  const [diagnosis, setDiagnosis] = useState("");
  const [investigations, setInvestigations] = useState("");
  const [treatmentPlan, setTreatmentPlan] = useState("");
  const [procedures, setProcedures] = useState("");
  const [followUpInst, setFollowUpInst] = useState("");
  const [followUpDate, setFollowUpDate] = useState("");
  const [internalNotes, setInternalNotes] = useState("");
  const [dischargeNotes, setDischargeNotes] = useState("");

  const [meds, setMeds] = useState<Medication[]>([]);
  const [arrivalVitals, setArrivalVitals] = useState<Vitals>({});
  const [dischargeVitals, setDischargeVitals] = useState<Vitals>({});

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const d = await api<Encounter>(`/api/v1/encounters/${encounterId}`);
      if (!d) throw new Error("Not found");
      setEnc(d);
      setComplaint(d.chief_complaint ?? "");
      setHpi(d.history_present_illness ?? "");
      setExam(d.examination_findings ?? "");
      setDiagnosis(d.diagnosis ?? "");
      setInvestigations(d.investigations ?? "");
      setTreatmentPlan(d.treatment_plan ?? "");
      setProcedures(d.procedures_performed ?? "");
      setFollowUpInst(d.follow_up_instructions ?? "");
      setFollowUpDate(d.follow_up_date ?? "");
      setInternalNotes(d.internal_notes ?? "");
      setDischargeNotes(d.discharge_notes ?? "");
      setMeds(d.medications ?? []);
      setArrivalVitals(d.arrival_vitals ?? {});
      setDischargeVitals(d.discharge_vitals ?? {});
    } catch (reason) {
      setError(errorMessage(reason, "Could not load encounter."));
    } finally {
      setLoading(false);
    }
  }, [encounterId]);

  useEffect(() => { void load(); }, [load]);

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!enc) return;
    setBusy(true);
    try {
      const body: Record<string, unknown> = { expected_version: enc.version };
      if (complaint !== (enc.chief_complaint ?? "")) body.chief_complaint = complaint || null;
      if (hpi !== (enc.history_present_illness ?? "")) body.history_present_illness = hpi || null;
      if (exam !== (enc.examination_findings ?? "")) body.examination_findings = exam || null;
      if (diagnosis !== (enc.diagnosis ?? "")) body.diagnosis = diagnosis || null;
      if (investigations !== (enc.investigations ?? "")) body.investigations = investigations || null;
      if (treatmentPlan !== (enc.treatment_plan ?? "")) body.treatment_plan = treatmentPlan || null;
      if (procedures !== (enc.procedures_performed ?? "")) body.procedures_performed = procedures || null;
      if (followUpInst !== (enc.follow_up_instructions ?? "")) body.follow_up_instructions = followUpInst || null;
      if (followUpDate !== (enc.follow_up_date ?? "")) body.follow_up_date = followUpDate || null;
      if (internalNotes !== (enc.internal_notes ?? "")) body.internal_notes = internalNotes || null;
      if (dischargeNotes !== (enc.discharge_notes ?? "")) body.discharge_notes = dischargeNotes || null;
      body.medications = meds;
      body.arrival_vitals = Object.values(arrivalVitals).some((v) => v != null && v !== "") ? arrivalVitals : null;
      body.discharge_vitals = Object.values(dischargeVitals).some((v) => v != null && v !== "") ? dischargeVitals : null;
      await api(`/api/v1/encounters/${encounterId}`, { method: "PATCH", headers: writeHeaders(), body: JSON.stringify(body) });
      toast.success("Encounter saved.");
      await load();
    } catch (reason) {
      toast.error(errorMessage(reason, "Could not save."));
    } finally {
      setBusy(false);
    }
  }

  async function changeStatus(newStatus: string) {
    if (!enc) return;
    if (newStatus === "finalized") {
      const yes = await confirm({ message: "Finalize this encounter? It will become read-only.", danger: true });
      if (!yes) return;
    }
    setBusy(true);
    try {
      await api(`/api/v1/encounters/${encounterId}/status`, { method: "POST", headers: writeHeaders(), body: JSON.stringify({ expected_version: enc.version, status: newStatus }) });
      toast.success(`Encounter ${newStatus === "finalized" ? "finalized" : "status updated"}.`);
      await load();
    } catch (reason) {
      toast.error(errorMessage(reason, "Could not update status."));
    } finally {
      setBusy(false);
    }
  }

  function addMed() { setMeds([...meds, { name: "", dosage: "", route: "oral", frequency: "", duration: "" }]); }
  function updateMed(idx: number, field: keyof Medication, val: string) {
    setMeds(meds.map((m, i) => i === idx ? { ...m, [field]: val } : m));
  }
  function removeMed(idx: number) { setMeds(meds.filter((_, i) => i !== idx)); }

  const pageRef = useRef<HTMLElement>(null);
  useEffect(() => {
    if (loading || !pageRef.current) return;
    anime({ targets: pageRef.current.querySelectorAll(".enc-section"), opacity: [0, 1], translateY: [16, 0], duration: 400, delay: anime.stagger(40, { start: 60 }), easing: "easeOutCubic" });
  }, [loading, tab]);

  if (loading) return <section className="dash-content"><div className="dashboard-empty" role="status"><strong>Loading encounter…</strong></div></section>;
  if (error || !enc) return <section className="dash-content"><div className="workspace-alert" role="alert"><strong>{error ?? "Encounter not found."}</strong></div><Link className="button button-secondary" href="/encounters">Back</Link></section>;

  const readonly = enc.status === "finalized";

  return (
    <section className="dash-content" ref={pageRef}>
      <div className="dash-topline">
        <div>
          <p className="eyebrow"><Link href="/encounters" style={{ color: "var(--muted)" }}>ENCOUNTERS</Link> · {typeLabel(enc.encounter_type).toUpperCase()}</p>
          <h1><Link href={`/patients/${enc.patient_id}`} style={{ color: "inherit" }}>{enc.patient_name}</Link></h1>
          <p style={{ color: "var(--muted)", marginTop: 4, fontSize: 13 }}>Dr. {enc.doctor_name}{enc.doctor_specialty && ` · ${enc.doctor_specialty}`}{enc.branch_name && ` · ${enc.branch_name}`}</p>
        </div>
        <div className="header-actions">
          <span style={{ fontSize: 11, padding: "3px 10px", borderRadius: 10, background: statusColor[enc.status] ?? "var(--line)", color: "#fff" }}>{enc.status === "in_review" ? "In Review" : typeLabel(enc.status)}</span>
          {enc.status === "draft" && <button className="button button-secondary" type="button" disabled={busy} onClick={() => void changeStatus("in_review")}>Send to review</button>}
          {enc.status === "in_review" && <button className="button button-primary" type="button" disabled={busy} onClick={() => void changeStatus("finalized")}>Finalize</button>}
          {enc.mrn && <span className="muted-mono">MRN: {enc.mrn}</span>}
        </div>
      </div>

      <div className="billing-summary">
        <div><span className="eyebrow">CREATED</span><strong style={{ fontSize: 13 }}>{fmtDateTime(enc.created_at)}</strong></div>
        {enc.finalized_at && <div><span className="eyebrow">FINALIZED</span><strong style={{ fontSize: 13 }}>{fmtDateTime(enc.finalized_at)}</strong></div>}
        <div><span className="eyebrow">TYPE</span><strong style={{ fontSize: 13 }}>{typeLabel(enc.encounter_type)}</strong></div>
      </div>

      <div className="pipeline-toolbar">
        <div className="pipeline-tabs" role="tablist">
          {(["assessment", "medications", "vitals", "discharge"] as const).map((t) => (
            <button key={t} className={tab === t ? "active" : ""} onClick={() => setTab(t)}>{t.charAt(0).toUpperCase() + t.slice(1)}</button>
          ))}
        </div>
      </div>

      <form onSubmit={(e) => void save(e)}>
        {tab === "assessment" && (
          <div className="enc-section surface-card">
            <div className="surface-card-heading"><div><p className="eyebrow">CLINICAL</p><h2>Assessment</h2></div></div>
            <div className="form-grid" style={{ gridTemplateColumns: "1fr" }}>
              <label>Chief complaint<textarea value={complaint} onChange={(e) => setComplaint(e.target.value)} rows={2} disabled={readonly} style={{ width: "100%", resize: "vertical" }} /></label>
              <label>History of present illness<textarea value={hpi} onChange={(e) => setHpi(e.target.value)} rows={3} disabled={readonly} style={{ width: "100%", resize: "vertical" }} /></label>
              <label>Examination findings<textarea value={exam} onChange={(e) => setExam(e.target.value)} rows={3} disabled={readonly} style={{ width: "100%", resize: "vertical" }} /></label>
              <label>Diagnosis<textarea value={diagnosis} onChange={(e) => setDiagnosis(e.target.value)} rows={2} disabled={readonly} style={{ width: "100%", resize: "vertical" }} /></label>
              <label>Investigations<textarea value={investigations} onChange={(e) => setInvestigations(e.target.value)} rows={2} disabled={readonly} style={{ width: "100%", resize: "vertical" }} /></label>
              <label>Treatment plan<textarea value={treatmentPlan} onChange={(e) => setTreatmentPlan(e.target.value)} rows={2} disabled={readonly} style={{ width: "100%", resize: "vertical" }} /></label>
              <label>Procedures performed<textarea value={procedures} onChange={(e) => setProcedures(e.target.value)} rows={2} disabled={readonly} style={{ width: "100%", resize: "vertical" }} /></label>
              <div className="form-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
                <label>Follow-up instructions<textarea value={followUpInst} onChange={(e) => setFollowUpInst(e.target.value)} rows={2} disabled={readonly} style={{ width: "100%", resize: "vertical" }} /></label>
                <label>Follow-up date<input type="date" value={followUpDate} onChange={(e) => setFollowUpDate(e.target.value)} disabled={readonly} /></label>
              </div>
              <label>Internal notes<textarea value={internalNotes} onChange={(e) => setInternalNotes(e.target.value)} rows={2} disabled={readonly} style={{ width: "100%", resize: "vertical", fontStyle: "italic" }} placeholder="Only visible to staff" /></label>
            </div>
          </div>
        )}

        {tab === "medications" && (
          <div className="enc-section surface-card">
            <div className="surface-card-heading"><div><p className="eyebrow">PRESCRIPTION</p><h2>Medications ({meds.length})</h2></div>
              {!readonly && <button className="button button-secondary" type="button" onClick={addMed}>Add medication</button>}
            </div>
            {meds.length === 0 && <div className="dashboard-empty"><strong>No medications</strong></div>}
            {meds.map((med, idx) => (
              <div key={idx} style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr 1fr 1fr auto", gap: 8, padding: "10px 0", borderBottom: "1px solid var(--line)", alignItems: "end" }}>
                <label style={{ fontSize: 11 }}>Name<input value={med.name} onChange={(e) => updateMed(idx, "name", e.target.value)} disabled={readonly} placeholder="Medication name" /></label>
                <label style={{ fontSize: 11 }}>Dosage<input value={med.dosage ?? ""} onChange={(e) => updateMed(idx, "dosage", e.target.value)} disabled={readonly} placeholder="e.g. 500mg" /></label>
                <label style={{ fontSize: 11 }}>Route<input value={med.route ?? ""} onChange={(e) => updateMed(idx, "route", e.target.value)} disabled={readonly} placeholder="oral/IV" /></label>
                <label style={{ fontSize: 11 }}>Frequency<input value={med.frequency ?? ""} onChange={(e) => updateMed(idx, "frequency", e.target.value)} disabled={readonly} placeholder="e.g. TDS" /></label>
                <label style={{ fontSize: 11 }}>Duration<input value={med.duration ?? ""} onChange={(e) => updateMed(idx, "duration", e.target.value)} disabled={readonly} placeholder="e.g. 5 days" /></label>
                {!readonly && <button className="ghost-button" type="button" style={{ color: "var(--coral)", fontSize: 11, marginBottom: 4 }} onClick={() => removeMed(idx)}>Remove</button>}
              </div>
            ))}
          </div>
        )}

        {tab === "vitals" && (
          <div className="enc-section surface-card">
            <div className="surface-card-heading"><div><p className="eyebrow">OBSERVATIONS</p><h2>Vitals</h2></div></div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
              <div>
                <p className="eyebrow" style={{ marginBottom: 12 }}>ARRIVAL VITALS</p>
                <VitalsForm vitals={arrivalVitals} onChange={setArrivalVitals} readonly={readonly} />
              </div>
              <div>
                <p className="eyebrow" style={{ marginBottom: 12 }}>DISCHARGE VITALS</p>
                <VitalsForm vitals={dischargeVitals} onChange={setDischargeVitals} readonly={readonly} />
              </div>
            </div>
          </div>
        )}

        {tab === "discharge" && (
          <div className="enc-section surface-card">
            <div className="surface-card-heading"><div><p className="eyebrow">DISCHARGE</p><h2>Discharge notes</h2></div></div>
            <div className="form-grid" style={{ gridTemplateColumns: "1fr" }}>
              <label>Discharge notes<textarea value={dischargeNotes} onChange={(e) => setDischargeNotes(e.target.value)} rows={4} disabled={readonly} style={{ width: "100%", resize: "vertical" }} /></label>
            </div>
          </div>
        )}

        {!readonly && (
          <div className="form-actions" style={{ marginTop: 16 }}>
            <button className="button button-primary" type="submit" disabled={busy}>{busy ? "Saving…" : "Save encounter"}</button>
          </div>
        )}
      </form>
    </section>
  );
}

function VitalsForm({ vitals, onChange, readonly }: { vitals: Vitals; onChange: (v: Vitals) => void; readonly: boolean }) {
  const set = (field: keyof Vitals, val: string) => {
    onChange({ ...vitals, [field]: val === "" ? undefined : (["pulse", "respiratory_rate", "oxygen_saturation"].includes(field) ? parseInt(val, 10) : ["temperature", "weight_kg", "height_cm"].includes(field) ? parseFloat(val) : val) });
  };
  return (
    <div className="form-grid">
      <label>Blood pressure<input value={vitals.blood_pressure ?? ""} onChange={(e) => set("blood_pressure", e.target.value)} disabled={readonly} placeholder="120/80" /></label>
      <label>Pulse (bpm)<input type="number" value={vitals.pulse ?? ""} onChange={(e) => set("pulse", e.target.value)} disabled={readonly} /></label>
      <label>Temperature (°C)<input type="number" step="0.1" value={vitals.temperature ?? ""} onChange={(e) => set("temperature", e.target.value)} disabled={readonly} /></label>
      <label>Respiratory rate<input type="number" value={vitals.respiratory_rate ?? ""} onChange={(e) => set("respiratory_rate", e.target.value)} disabled={readonly} /></label>
      <label>SpO2 (%)<input type="number" value={vitals.oxygen_saturation ?? ""} onChange={(e) => set("oxygen_saturation", e.target.value)} disabled={readonly} /></label>
      <label>Weight (kg)<input type="number" step="0.1" value={vitals.weight_kg ?? ""} onChange={(e) => set("weight_kg", e.target.value)} disabled={readonly} /></label>
      <label>Height (cm)<input type="number" step="0.1" value={vitals.height_cm ?? ""} onChange={(e) => set("height_cm", e.target.value)} disabled={readonly} /></label>
      <label>Notes<input value={vitals.notes ?? ""} onChange={(e) => set("notes", e.target.value)} disabled={readonly} /></label>
    </div>
  );
}
