"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { api, errorMessage, writeHeaders } from "../../_lib/client";
import { useToast } from "../../_lib/toast";
import { useConfirm } from "../../_lib/confirm";

/* ── Types ─────────────────────────────────────────────────────────── */
type Vitals = { blood_pressure?: string; pulse?: number; temperature?: number; respiratory_rate?: number; oxygen_saturation?: number; weight_kg?: number; height_cm?: number; notes?: string };
type Medication = { name: string; dosage?: string; route?: string; frequency?: string; duration?: string; notes?: string };
type AdministeredTreatment = { name: string; dosage?: string; route?: string; administered_at?: string; administered_by?: string; response?: string; notes?: string };
type AdministeredProcedure = { name: string; performed_at?: string; performer?: string; findings?: string; notes?: string };
type AmendmentEntry = { field: string; old_value: string | null; new_value: string; reason: string; amended_by: string; amended_at: string };

type Encounter = {
  id: string; clinic_id: string; patient_id: string; patient_name: string; mrn: string | null;
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
  // Arrival
  arrival_mode: string | null; arrival_datetime: string | null;
  attendant_name: string | null; attendant_phone: string | null;
  condition_on_arrival: string | null;
  // Clinical
  known_allergies: string | null; allergy_status: string;
  medical_history: string | null; current_medications_text: string | null;
  symptom_duration: string | null;
  gcs_eye: number | null; gcs_verbal: number | null; gcs_motor: number | null;
  pain_score: number | null;
  investigation_results: string | null; clinical_assessment: string | null;
  // Administered
  administered_treatments: AdministeredTreatment[] | null;
  administered_procedures: AdministeredProcedure[] | null;
  treatment_response: string | null; adverse_reactions: string | null;
  // Discharge extension
  discharge_condition: string | null; discharge_outcome: string | null;
  discharge_destination: string | null; discharge_reason: string | null;
  discharge_datetime: string | null; discharged_by: string | null;
  discharge_instructions: string | null; warning_signs: string | null;
  medicine_guidance: string | null;
  follow_up_clinician: string | null; follow_up_department: string | null;
  referral_instructions: string | null;
  amendment_history: AmendmentEntry[] | null;
  // Patient data from JOIN
  patient_dob: string | null; patient_allergies: string | null;
  patient_contraindications: string | null;
  emergency_contact_name: string | null; emergency_contact_phone: string | null;
  emergency_contact_relation: string | null;
};

/* ── Helpers ───────────────────────────────────────────────────────── */
const fmtDate = (v: string) => new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(v));
const fmtDateTime = (v: string) => new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(v));
const typeLabel = (v: string) => v.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
const statusColor: Record<string, string> = {
  draft: "#e0a458", in_progress: "var(--accent)", ready_for_discharge: "#5886b4",
  discharged: "var(--leaf)", finalized: "#3c5149", referred: "#8468a8", transferred: "#4c7d91",
};
const statusLabel: Record<string, string> = {
  draft: "Draft", in_progress: "In Progress", ready_for_discharge: "Ready for Discharge",
  discharged: "Discharged", finalized: "Finalized", referred: "Referred", transferred: "Transferred",
};

function computeAge(dob: string | null): string {
  if (!dob) return "";
  const birth = new Date(dob);
  if (isNaN(birth.getTime())) return "";
  const now = new Date();
  let years = now.getFullYear() - birth.getFullYear();
  let months = now.getMonth() - birth.getMonth();
  if (now.getDate() < birth.getDate()) months--;
  if (months < 0) { years--; months += 12; }
  return years < 2 ? `${years * 12 + months}mo` : months > 0 ? `${years}y ${months}mo` : `${years}y`;
}

function toLocalDatetime(iso: string | null): string {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0") + "T" + String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0");
  } catch { return ""; }
}

type Prescription = { id: string; medication_name: string; dosage: string | null; frequency: string | null; duration: string | null; instructions: string | null; status: string; prescribed_at: string };

type Tab = "arrival" | "patient" | "assessment" | "treatment" | "medications" | "vitals" | "discharge" | "prescriptions" | "summary";
const TABS: Tab[] = ["arrival", "patient", "assessment", "treatment", "medications", "vitals", "discharge", "prescriptions", "summary"];

const AMENDABLE_FIELDS = [
  { value: "chief_complaint", label: "Chief Complaint" },
  { value: "history_present_illness", label: "History of Present Illness" },
  { value: "examination_findings", label: "Examination Findings" },
  { value: "diagnosis", label: "Diagnosis" },
  { value: "investigations", label: "Investigations" },
  { value: "treatment_plan", label: "Treatment Plan" },
  { value: "procedures_performed", label: "Procedures Performed" },
  { value: "follow_up_instructions", label: "Follow-up Instructions" },
  { value: "discharge_notes", label: "Discharge Notes" },
  { value: "discharge_instructions", label: "Discharge Instructions" },
  { value: "clinical_assessment", label: "Clinical Assessment" },
  { value: "investigation_results", label: "Investigation Results" },
  { value: "treatment_response", label: "Treatment Response" },
];

/* ── Main Component ────────────────────────────────────────────────── */
export default function EncounterDetailPage() {
  const { encounterId } = useParams<{ encounterId: string }>();
  const toast = useToast();
  const confirm = useConfirm();

  const [enc, setEnc] = useState<Encounter | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<Tab>("arrival");

  // Assessment
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
  const [symptomDuration, setSymptomDuration] = useState("");
  const [gcsEye, setGcsEye] = useState<number | null>(null);
  const [gcsVerbal, setGcsVerbal] = useState<number | null>(null);
  const [gcsMotor, setGcsMotor] = useState<number | null>(null);
  const [painScore, setPainScore] = useState<number | null>(null);
  const [investigationResults, setInvestigationResults] = useState("");
  const [clinicalAssessment, setClinicalAssessment] = useState("");

  // Arrival
  const [arrivalMode, setArrivalMode] = useState("");
  const [arrivalDatetime, setArrivalDatetime] = useState("");
  const [attendantName, setAttendantName] = useState("");
  const [attendantPhone, setAttendantPhone] = useState("");
  const [conditionOnArrival, setConditionOnArrival] = useState("");

  // Patient summary (editable fields on the encounter)
  const [knownAllergies, setKnownAllergies] = useState("");
  const [allergyStatus, setAllergyStatus] = useState("unknown");
  const [medicalHistory, setMedicalHistory] = useState("");
  const [currentMedsText, setCurrentMedsText] = useState("");

  // Medications & vitals
  const [meds, setMeds] = useState<Medication[]>([]);
  const [arrivalVitals, setArrivalVitals] = useState<Vitals>({});
  const [dischargeVitals, setDischargeVitals] = useState<Vitals>({});

  // Administered
  const [treatments, setTreatments] = useState<AdministeredTreatment[]>([]);
  const [adminProcedures, setAdminProcedures] = useState<AdministeredProcedure[]>([]);
  const [treatmentResponse, setTreatmentResponse] = useState("");
  const [adverseReactions, setAdverseReactions] = useState("");

  // Discharge extension
  const [dischCondition, setDischCondition] = useState("");
  const [dischOutcome, setDischOutcome] = useState("");
  const [dischDestination, setDischDestination] = useState("");
  const [dischReason, setDischReason] = useState("");
  const [dischInstructions, setDischInstructions] = useState("");
  const [warningSigns, setWarningSigns] = useState("");
  const [medicineGuidance, setMedicineGuidance] = useState("");
  const [followUpClinician, setFollowUpClinician] = useState("");
  const [followUpDept, setFollowUpDept] = useState("");
  const [referralInstructions, setReferralInstructions] = useState("");

  // Prescriptions
  const [prescriptions, setPrescriptions] = useState<Prescription[]>([]);
  const [prescriptionsLoaded, setPrescriptionsLoaded] = useState(false);

  // Amendment
  const [amendField, setAmendField] = useState("");
  const [amendNewValue, setAmendNewValue] = useState("");
  const [amendReason, setAmendReason] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const d = await api<Encounter>(`/api/v1/encounters/${encounterId}`);
      if (!d) throw new Error("Not found");
      setEnc(d);
      // Assessment
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
      setSymptomDuration(d.symptom_duration ?? "");
      setGcsEye(d.gcs_eye);
      setGcsVerbal(d.gcs_verbal);
      setGcsMotor(d.gcs_motor);
      setPainScore(d.pain_score);
      setInvestigationResults(d.investigation_results ?? "");
      setClinicalAssessment(d.clinical_assessment ?? "");
      // Arrival
      setArrivalMode(d.arrival_mode ?? "");
      setArrivalDatetime(toLocalDatetime(d.arrival_datetime));
      setAttendantName(d.attendant_name ?? "");
      setAttendantPhone(d.attendant_phone ?? "");
      setConditionOnArrival(d.condition_on_arrival ?? "");
      // Patient summary
      setKnownAllergies(d.known_allergies ?? "");
      setAllergyStatus(d.allergy_status ?? "unknown");
      setMedicalHistory(d.medical_history ?? "");
      setCurrentMedsText(d.current_medications_text ?? "");
      // Meds & vitals
      setMeds(d.medications ?? []);
      setArrivalVitals(d.arrival_vitals ?? {});
      setDischargeVitals(d.discharge_vitals ?? {});
      // Administered
      setTreatments(d.administered_treatments ?? []);
      setAdminProcedures(d.administered_procedures ?? []);
      setTreatmentResponse(d.treatment_response ?? "");
      setAdverseReactions(d.adverse_reactions ?? "");
      // Discharge
      setDischCondition(d.discharge_condition ?? "");
      setDischOutcome(d.discharge_outcome ?? "");
      setDischDestination(d.discharge_destination ?? "");
      setDischReason(d.discharge_reason ?? "");
      setDischInstructions(d.discharge_instructions ?? "");
      setWarningSigns(d.warning_signs ?? "");
      setMedicineGuidance(d.medicine_guidance ?? "");
      setFollowUpClinician(d.follow_up_clinician ?? "");
      setFollowUpDept(d.follow_up_department ?? "");
      setReferralInstructions(d.referral_instructions ?? "");
    } catch (reason) {
      setError(errorMessage(reason, "Could not load encounter."));
    } finally { setLoading(false); }
  }, [encounterId]);

  useEffect(() => { void load(); }, [load]);

  /* ── Save (PATCH) ─────────────────────────────────────────────── */
  async function save(e: FormEvent) {
    e.preventDefault();
    if (!enc) return;
    setBusy(true);
    try {
      const body: Record<string, unknown> = { expected_version: enc.version };
      const s = (field: string, local: string, remote: string | null) => { if (local !== (remote ?? "")) body[field] = local || null; };
      // Assessment
      s("chief_complaint", complaint, enc.chief_complaint);
      s("history_present_illness", hpi, enc.history_present_illness);
      s("examination_findings", exam, enc.examination_findings);
      s("diagnosis", diagnosis, enc.diagnosis);
      s("investigations", investigations, enc.investigations);
      s("treatment_plan", treatmentPlan, enc.treatment_plan);
      s("procedures_performed", procedures, enc.procedures_performed);
      s("follow_up_instructions", followUpInst, enc.follow_up_instructions);
      s("follow_up_date", followUpDate, enc.follow_up_date);
      s("internal_notes", internalNotes, enc.internal_notes);
      s("discharge_notes", dischargeNotes, enc.discharge_notes);
      s("symptom_duration", symptomDuration, enc.symptom_duration);
      s("investigation_results", investigationResults, enc.investigation_results);
      s("clinical_assessment", clinicalAssessment, enc.clinical_assessment);
      // GCS / pain
      if (gcsEye !== enc.gcs_eye) body.gcs_eye = gcsEye;
      if (gcsVerbal !== enc.gcs_verbal) body.gcs_verbal = gcsVerbal;
      if (gcsMotor !== enc.gcs_motor) body.gcs_motor = gcsMotor;
      if (painScore !== enc.pain_score) body.pain_score = painScore;
      // Arrival
      s("arrival_mode", arrivalMode, enc.arrival_mode);
      if (arrivalDatetime !== toLocalDatetime(enc.arrival_datetime)) body.arrival_datetime = arrivalDatetime ? new Date(arrivalDatetime).toISOString() : null;
      s("attendant_name", attendantName, enc.attendant_name);
      s("attendant_phone", attendantPhone, enc.attendant_phone);
      s("condition_on_arrival", conditionOnArrival, enc.condition_on_arrival);
      // Patient summary
      s("known_allergies", knownAllergies, enc.known_allergies);
      if (allergyStatus !== (enc.allergy_status ?? "unknown")) body.allergy_status = allergyStatus;
      s("medical_history", medicalHistory, enc.medical_history);
      s("current_medications_text", currentMedsText, enc.current_medications_text);
      // Administered
      body.administered_treatments = treatments;
      body.administered_procedures = adminProcedures;
      s("treatment_response", treatmentResponse, enc.treatment_response);
      s("adverse_reactions", adverseReactions, enc.adverse_reactions);
      // Discharge text fields
      s("discharge_condition", dischCondition, enc.discharge_condition);
      if (dischOutcome !== (enc.discharge_outcome ?? "")) body.discharge_outcome = dischOutcome || null;
      s("discharge_destination", dischDestination, enc.discharge_destination);
      s("discharge_reason", dischReason, enc.discharge_reason);
      s("discharge_instructions", dischInstructions, enc.discharge_instructions);
      s("warning_signs", warningSigns, enc.warning_signs);
      s("medicine_guidance", medicineGuidance, enc.medicine_guidance);
      s("follow_up_clinician", followUpClinician, enc.follow_up_clinician);
      s("follow_up_department", followUpDept, enc.follow_up_department);
      s("referral_instructions", referralInstructions, enc.referral_instructions);
      // Meds & vitals
      body.medications = meds;
      body.arrival_vitals = Object.values(arrivalVitals).some((v) => v != null && v !== "") ? arrivalVitals : null;
      body.discharge_vitals = Object.values(dischargeVitals).some((v) => v != null && v !== "") ? dischargeVitals : null;

      await api(`/api/v1/encounters/${encounterId}`, { method: "PATCH", headers: writeHeaders(), body: JSON.stringify(body) });
      toast.success("Encounter saved.");
      await load();
    } catch (reason) {
      toast.error(errorMessage(reason, "Could not save."));
    } finally { setBusy(false); }
  }

  /* ── Status change ────────────────────────────────────────────── */
  async function changeStatus(newStatus: string) {
    if (!enc) return;
    if (newStatus === "finalized") {
      const yes = await confirm({ message: "Finalize this encounter? It will become permanently read-only.", danger: true });
      if (!yes) return;
    }
    setBusy(true);
    try {
      await api(`/api/v1/encounters/${encounterId}/status`, { method: "POST", headers: writeHeaders(), body: JSON.stringify({ expected_version: enc.version, status: newStatus }) });
      toast.success(`Status updated to ${statusLabel[newStatus] ?? newStatus}.`);
      await load();
    } catch (reason) {
      toast.error(errorMessage(reason, "Could not update status."));
    } finally { setBusy(false); }
  }

  /* ── Discharge ────────────────────────────────────────────────── */
  async function completeDischarge() {
    if (!enc) return;
    if (!dischOutcome) { toast.error("Please select a discharge outcome."); return; }
    const yes = await confirm({ message: "Complete discharge? The encounter will be marked as discharged.", danger: true });
    if (!yes) return;
    setBusy(true);
    try {
      const body: Record<string, unknown> = {
        expected_version: enc.version,
        discharge_outcome: dischOutcome,
        discharge_condition: dischCondition || null,
        discharge_destination: dischDestination || null,
        discharge_reason: dischReason || null,
        discharge_notes: dischargeNotes || null,
        discharge_instructions: dischInstructions || null,
        warning_signs: warningSigns || null,
        medicine_guidance: medicineGuidance || null,
        follow_up_date: followUpDate || null,
        follow_up_instructions: followUpInst || null,
        follow_up_clinician: followUpClinician || null,
        follow_up_department: followUpDept || null,
        referral_instructions: referralInstructions || null,
      };
      const dv = Object.values(dischargeVitals).some((v) => v != null && v !== "") ? dischargeVitals : null;
      if (dv) body.discharge_vitals = dv;
      await api(`/api/v1/encounters/${encounterId}/discharge`, { method: "POST", headers: writeHeaders(), body: JSON.stringify(body) });
      toast.success("Patient discharged successfully.");
      await load();
    } catch (reason) {
      toast.error(errorMessage(reason, "Could not complete discharge."));
    } finally { setBusy(false); }
  }

  /* ── Amend ────────────────────────────────────────────────────── */
  async function submitAmendment() {
    if (!enc || !amendField || !amendNewValue || !amendReason) { toast.error("All amendment fields are required."); return; }
    setBusy(true);
    try {
      const oldVal = (enc as Record<string, unknown>)[amendField];
      await api(`/api/v1/encounters/${encounterId}/amend`, { method: "POST", headers: writeHeaders(), body: JSON.stringify({ expected_version: enc.version, field: amendField, old_value: typeof oldVal === "string" ? oldVal : null, new_value: amendNewValue, reason: amendReason }) });
      toast.success("Amendment recorded.");
      setAmendField(""); setAmendNewValue(""); setAmendReason("");
      await load();
    } catch (reason) {
      toast.error(errorMessage(reason, "Could not submit amendment."));
    } finally { setBusy(false); }
  }

  /* ── Load prescriptions (lazy) ─────────────────────────────── */
  const loadPrescriptions = useCallback(async () => {
    try {
      const data = await api<Prescription[]>(`/api/v1/encounters/${encounterId}/prescriptions`);
      setPrescriptions(data ?? []);
    } catch { /* silent — tab shows empty state */ }
    setPrescriptionsLoaded(true);
  }, [encounterId]);

  useEffect(() => {
    if (tab === "prescriptions" && !prescriptionsLoaded) void loadPrescriptions();
  }, [tab, prescriptionsLoaded, loadPrescriptions]);

  /* ── Medication helpers ───────────────────────────────────────── */
  function addMed() { setMeds([...meds, { name: "", dosage: "", route: "oral", frequency: "", duration: "" }]); }
  function updateMed(idx: number, field: keyof Medication, val: string) { setMeds(meds.map((m, i) => i === idx ? { ...m, [field]: val } : m)); }
  function removeMed(idx: number) { setMeds(meds.filter((_, i) => i !== idx)); }

  /* ── Treatment helpers ────────────────────────────────────────── */
  function addTreatment() { setTreatments([...treatments, { name: "", dosage: "", route: "", administered_at: "", administered_by: "", response: "", notes: "" }]); }
  function updateTreatment(idx: number, field: keyof AdministeredTreatment, val: string) { setTreatments(treatments.map((t, i) => i === idx ? { ...t, [field]: val } : t)); }
  function removeTreatment(idx: number) { setTreatments(treatments.filter((_, i) => i !== idx)); }

  function addProcedure() { setAdminProcedures([...adminProcedures, { name: "", performed_at: "", performer: "", findings: "", notes: "" }]); }
  function updateProcedure(idx: number, field: keyof AdministeredProcedure, val: string) { setAdminProcedures(adminProcedures.map((p, i) => i === idx ? { ...p, [field]: val } : p)); }
  function removeProcedure(idx: number) { setAdminProcedures(adminProcedures.filter((_, i) => i !== idx)); }

  const pageRef = useRef<HTMLElement>(null);

  /* ── Loading / Error ──────────────────────────────────────────── */
  if (loading) return <section className="dash-content"><div className="dashboard-empty" role="status"><strong>Loading encounter...</strong></div></section>;
  if (error || !enc) return <section className="dash-content"><div className="workspace-alert" role="alert"><strong>{error ?? "Encounter not found."}</strong></div><Link className="button button-secondary" href="/encounters">Back</Link></section>;

  const readonly = enc.status === "discharged" || enc.status === "finalized";

  /* ── Render ───────────────────────────────────────────────────── */
  return (
    <section className="dash-content" ref={pageRef}>
      {/* Header */}
      <div className="dash-topline">
        <div>
          <p className="eyebrow"><Link href="/encounters" style={{ color: "var(--muted)" }}>ENCOUNTERS</Link> &middot; {typeLabel(enc.encounter_type).toUpperCase()}</p>
          <h1><Link href={`/patients/${enc.patient_id}`} style={{ color: "inherit" }}>{enc.patient_name}</Link></h1>
          <p style={{ color: "var(--muted)", marginTop: 4, fontSize: 13 }}>Dr. {enc.doctor_name}{enc.doctor_specialty && ` · ${enc.doctor_specialty}`}{enc.branch_name && ` · ${enc.branch_name}`}</p>
        </div>
        <div className="header-actions">
          <span style={{ fontSize: 11, padding: "3px 10px", borderRadius: 10, background: statusColor[enc.status] ?? "var(--line)", color: "#fff" }}>{statusLabel[enc.status] ?? typeLabel(enc.status)}</span>
          {enc.status === "draft" && <button className="button button-secondary" type="button" disabled={busy} onClick={() => void changeStatus("in_progress")}>Begin Assessment</button>}
          {enc.status === "in_progress" && <button className="button button-secondary" type="button" disabled={busy} onClick={() => void changeStatus("ready_for_discharge")}>Ready for Discharge</button>}
          {enc.status === "discharged" && <button className="button button-primary" type="button" disabled={busy} onClick={() => void changeStatus("finalized")}>Finalize</button>}
          {enc.mrn && <span className="muted-mono">MRN: {enc.mrn}</span>}
        </div>
      </div>

      {/* Summary bar */}
      <div className="billing-summary">
        <div><span className="eyebrow">CREATED</span><strong style={{ fontSize: 13 }}>{fmtDateTime(enc.created_at)}</strong></div>
        {enc.discharge_datetime && <div><span className="eyebrow">DISCHARGED</span><strong style={{ fontSize: 13 }}>{fmtDateTime(enc.discharge_datetime)}</strong></div>}
        {enc.finalized_at && <div><span className="eyebrow">FINALIZED</span><strong style={{ fontSize: 13 }}>{fmtDateTime(enc.finalized_at)}</strong></div>}
        <div><span className="eyebrow">TYPE</span><strong style={{ fontSize: 13 }}>{typeLabel(enc.encounter_type)}</strong></div>
      </div>

      {/* Tabs */}
      <div className="pipeline-toolbar">
        <div className="pipeline-tabs" role="tablist">
          {TABS.map((t) => (
            <button key={t} className={tab === t ? "active" : ""} onClick={() => setTab(t)}>{typeLabel(t)}</button>
          ))}
        </div>
      </div>

      <form onSubmit={(e) => void save(e)}>

        {/* ── Tab A: Arrival ─────────────────────────────────────── */}
        {tab === "arrival" && (
          <div className="enc-section surface-card">
            <div className="surface-card-heading"><div><p className="eyebrow">ARRIVAL</p><h2>Arrival Information</h2></div></div>
            <div className="form-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
              <label>Arrival mode
                <select value={arrivalMode} onChange={(e) => setArrivalMode(e.target.value)} disabled={readonly}>
                  <option value="">Select...</option>
                  <option value="walk_in">Walk-in</option>
                  <option value="ambulance">Ambulance</option>
                  <option value="referral">Referral</option>
                  <option value="transfer">Transfer</option>
                  <option value="self">Self</option>
                </select>
              </label>
              <label>Arrival date/time<input type="datetime-local" value={arrivalDatetime} onChange={(e) => setArrivalDatetime(e.target.value)} disabled={readonly} /></label>
              <label>Attendant name<input value={attendantName} onChange={(e) => setAttendantName(e.target.value)} disabled={readonly} placeholder="Name of accompanying person" /></label>
              <label>Attendant phone<input value={attendantPhone} onChange={(e) => setAttendantPhone(e.target.value)} disabled={readonly} placeholder="Phone number" /></label>
            </div>
            <div className="form-grid" style={{ gridTemplateColumns: "1fr", marginTop: 12 }}>
              <label>Condition on arrival<textarea value={conditionOnArrival} onChange={(e) => setConditionOnArrival(e.target.value)} rows={2} disabled={readonly} style={{ width: "100%", resize: "vertical" }} placeholder="Patient's condition when they arrived" /></label>
            </div>
            <div style={{ marginTop: 16 }}>
              <p className="eyebrow" style={{ marginBottom: 12 }}>ARRIVAL VITALS</p>
              <VitalsForm vitals={arrivalVitals} onChange={setArrivalVitals} readonly={readonly} />
            </div>
          </div>
        )}

        {/* ── Tab B: Patient Summary ─────────────────────────────── */}
        {tab === "patient" && (
          <div className="enc-section surface-card">
            <div className="surface-card-heading"><div><p className="eyebrow">PATIENT</p><h2>Patient Summary</h2></div></div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 20, padding: "12px 16px", background: "var(--bg-alt, var(--surface-alt, rgba(0,0,0,0.03)))", borderRadius: 8 }}>
              <div><span className="eyebrow">NAME</span><p style={{ fontWeight: 600 }}>{enc.patient_name}</p></div>
              <div><span className="eyebrow">MRN</span><p>{enc.mrn ?? "N/A"}</p></div>
              <div><span className="eyebrow">DATE OF BIRTH</span><p>{enc.patient_dob ? `${fmtDate(enc.patient_dob)} (${computeAge(enc.patient_dob)})` : "N/A"}</p></div>
              <div><span className="eyebrow">ALLERGIES (PATIENT RECORD)</span><p>{enc.patient_allergies || "None on file"}</p></div>
              <div><span className="eyebrow">CONTRAINDICATIONS</span><p>{enc.patient_contraindications || "None on file"}</p></div>
              <div><span className="eyebrow">EMERGENCY CONTACT</span><p>{enc.emergency_contact_name ? `${enc.emergency_contact_name}${enc.emergency_contact_relation ? ` (${enc.emergency_contact_relation})` : ""} ${enc.emergency_contact_phone ?? ""}` : "None on file"}</p></div>
            </div>
            <div className="form-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
              <label>Allergy status
                <select value={allergyStatus} onChange={(e) => setAllergyStatus(e.target.value)} disabled={readonly}>
                  <option value="unknown">Unknown</option>
                  <option value="none_known">No Known Allergies (NKA)</option>
                  <option value="has_allergies">Has Allergies</option>
                </select>
              </label>
              <label>Known allergies (this encounter)<input value={knownAllergies} onChange={(e) => setKnownAllergies(e.target.value)} disabled={readonly} placeholder="List known allergies" /></label>
            </div>
            <div className="form-grid" style={{ gridTemplateColumns: "1fr", marginTop: 12 }}>
              <label>Medical history<textarea value={medicalHistory} onChange={(e) => setMedicalHistory(e.target.value)} rows={3} disabled={readonly} style={{ width: "100%", resize: "vertical" }} placeholder="Relevant past medical history" /></label>
              <label>Current medications<textarea value={currentMedsText} onChange={(e) => setCurrentMedsText(e.target.value)} rows={2} disabled={readonly} style={{ width: "100%", resize: "vertical" }} placeholder="Medications patient is currently taking" /></label>
            </div>
          </div>
        )}

        {/* ── Tab C: Assessment ──────────────────────────────────── */}
        {tab === "assessment" && (
          <div className="enc-section surface-card">
            <div className="surface-card-heading"><div><p className="eyebrow">CLINICAL</p><h2>Assessment</h2></div></div>
            <div className="form-grid" style={{ gridTemplateColumns: "1fr" }}>
              <label>Chief complaint<textarea value={complaint} onChange={(e) => setComplaint(e.target.value)} rows={2} disabled={readonly} style={{ width: "100%", resize: "vertical" }} /></label>
              <label>History of present illness<textarea value={hpi} onChange={(e) => setHpi(e.target.value)} rows={3} disabled={readonly} style={{ width: "100%", resize: "vertical" }} /></label>
              <div className="form-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
                <label>Symptom duration<input value={symptomDuration} onChange={(e) => setSymptomDuration(e.target.value)} disabled={readonly} placeholder="e.g. 3 days" /></label>
                <label>Pain score (0-10)
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <input type="number" min={0} max={10} value={painScore ?? ""} onChange={(e) => setPainScore(e.target.value === "" ? null : parseInt(e.target.value, 10))} disabled={readonly} style={{ width: 80 }} />
                    {painScore != null && <span style={{ fontSize: 12, fontWeight: 600, color: painScore <= 3 ? "var(--leaf)" : painScore <= 6 ? "#e0a458" : "var(--coral)" }}>{painScore <= 3 ? "Mild" : painScore <= 6 ? "Moderate" : "Severe"}</span>}
                  </div>
                </label>
              </div>
              <label>Examination findings<textarea value={exam} onChange={(e) => setExam(e.target.value)} rows={3} disabled={readonly} style={{ width: "100%", resize: "vertical" }} /></label>
            </div>
            <GCSCalculator eye={gcsEye} verbal={gcsVerbal} motor={gcsMotor} onChange={(f, v) => { if (f === "eye") setGcsEye(v); else if (f === "verbal") setGcsVerbal(v); else setGcsMotor(v); }} readonly={readonly} />
            <div className="form-grid" style={{ gridTemplateColumns: "1fr", marginTop: 12 }}>
              <label>Investigations<textarea value={investigations} onChange={(e) => setInvestigations(e.target.value)} rows={2} disabled={readonly} style={{ width: "100%", resize: "vertical" }} /></label>
              <label>Investigation results<textarea value={investigationResults} onChange={(e) => setInvestigationResults(e.target.value)} rows={2} disabled={readonly} style={{ width: "100%", resize: "vertical" }} /></label>
              <label>Diagnosis<textarea value={diagnosis} onChange={(e) => setDiagnosis(e.target.value)} rows={2} disabled={readonly} style={{ width: "100%", resize: "vertical" }} /></label>
              <label>Clinical assessment<textarea value={clinicalAssessment} onChange={(e) => setClinicalAssessment(e.target.value)} rows={2} disabled={readonly} style={{ width: "100%", resize: "vertical" }} /></label>
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

        {/* ── Tab D: Administered Treatment ──────────────────────── */}
        {tab === "treatment" && (
          <>
            <div className="enc-section surface-card">
              <div className="surface-card-heading"><div><p className="eyebrow">ADMINISTERED</p><h2>Treatments ({treatments.length})</h2></div>
                {!readonly && <button className="button button-secondary" type="button" onClick={addTreatment}>Add treatment</button>}
              </div>
              {treatments.length === 0 && <div className="dashboard-empty"><strong>No administered treatments</strong></div>}
              {treatments.map((t, idx) => (
                <div key={idx} style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr 1fr 1fr 1fr auto", gap: 8, padding: "10px 0", borderBottom: "1px solid var(--line)", alignItems: "end" }}>
                  <label style={{ fontSize: 11 }}>Name<input value={t.name} onChange={(e) => updateTreatment(idx, "name", e.target.value)} disabled={readonly} placeholder="Treatment name" /></label>
                  <label style={{ fontSize: 11 }}>Dosage<input value={t.dosage ?? ""} onChange={(e) => updateTreatment(idx, "dosage", e.target.value)} disabled={readonly} placeholder="e.g. 500mg" /></label>
                  <label style={{ fontSize: 11 }}>Route<input value={t.route ?? ""} onChange={(e) => updateTreatment(idx, "route", e.target.value)} disabled={readonly} placeholder="oral/IV" /></label>
                  <label style={{ fontSize: 11 }}>Given at<input type="datetime-local" value={t.administered_at ?? ""} onChange={(e) => updateTreatment(idx, "administered_at", e.target.value)} disabled={readonly} /></label>
                  <label style={{ fontSize: 11 }}>Given by<input value={t.administered_by ?? ""} onChange={(e) => updateTreatment(idx, "administered_by", e.target.value)} disabled={readonly} /></label>
                  <label style={{ fontSize: 11 }}>Response<input value={t.response ?? ""} onChange={(e) => updateTreatment(idx, "response", e.target.value)} disabled={readonly} /></label>
                  {!readonly && <button className="ghost-button" type="button" style={{ color: "var(--coral)", fontSize: 11, marginBottom: 4 }} onClick={() => removeTreatment(idx)}>Remove</button>}
                </div>
              ))}
            </div>
            <div className="enc-section surface-card" style={{ marginTop: 16 }}>
              <div className="surface-card-heading"><div><p className="eyebrow">PROCEDURES</p><h2>Administered Procedures ({adminProcedures.length})</h2></div>
                {!readonly && <button className="button button-secondary" type="button" onClick={addProcedure}>Add procedure</button>}
              </div>
              {adminProcedures.length === 0 && <div className="dashboard-empty"><strong>No administered procedures</strong></div>}
              {adminProcedures.map((p, idx) => (
                <div key={idx} style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr 2fr auto", gap: 8, padding: "10px 0", borderBottom: "1px solid var(--line)", alignItems: "end" }}>
                  <label style={{ fontSize: 11 }}>Name<input value={p.name} onChange={(e) => updateProcedure(idx, "name", e.target.value)} disabled={readonly} placeholder="Procedure name" /></label>
                  <label style={{ fontSize: 11 }}>Performed at<input type="datetime-local" value={p.performed_at ?? ""} onChange={(e) => updateProcedure(idx, "performed_at", e.target.value)} disabled={readonly} /></label>
                  <label style={{ fontSize: 11 }}>Performer<input value={p.performer ?? ""} onChange={(e) => updateProcedure(idx, "performer", e.target.value)} disabled={readonly} /></label>
                  <label style={{ fontSize: 11 }}>Findings<input value={p.findings ?? ""} onChange={(e) => updateProcedure(idx, "findings", e.target.value)} disabled={readonly} /></label>
                  {!readonly && <button className="ghost-button" type="button" style={{ color: "var(--coral)", fontSize: 11, marginBottom: 4 }} onClick={() => removeProcedure(idx)}>Remove</button>}
                </div>
              ))}
            </div>
            <div className="enc-section surface-card" style={{ marginTop: 16 }}>
              <div className="surface-card-heading"><div><p className="eyebrow">RESPONSE</p><h2>Treatment Response</h2></div></div>
              <div className="form-grid" style={{ gridTemplateColumns: "1fr" }}>
                <label>Treatment response<textarea value={treatmentResponse} onChange={(e) => setTreatmentResponse(e.target.value)} rows={2} disabled={readonly} style={{ width: "100%", resize: "vertical" }} placeholder="How the patient responded to treatment" /></label>
                <label>Adverse reactions<textarea value={adverseReactions} onChange={(e) => setAdverseReactions(e.target.value)} rows={2} disabled={readonly} style={{ width: "100%", resize: "vertical" }} placeholder="Any adverse reactions observed" /></label>
              </div>
            </div>
          </>
        )}

        {/* ── Tab E: Medications ─────────────────────────────────── */}
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

        {/* ── Tab F: Vitals ──────────────────────────────────────── */}
        {tab === "vitals" && (
          <div className="enc-section surface-card">
            <div className="surface-card-heading"><div><p className="eyebrow">OBSERVATIONS</p><h2>Vitals</h2></div></div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
              <div>
                <p className="eyebrow" style={{ marginBottom: 12 }}>ARRIVAL VITALS</p>
                <VitalsForm vitals={arrivalVitals} onChange={setArrivalVitals} readonly={readonly} />
                <BMIDisplay vitals={arrivalVitals} label="Arrival" />
              </div>
              <div>
                <p className="eyebrow" style={{ marginBottom: 12 }}>DISCHARGE VITALS</p>
                <VitalsForm vitals={dischargeVitals} onChange={setDischargeVitals} readonly={readonly} />
                <BMIDisplay vitals={dischargeVitals} label="Discharge" />
              </div>
            </div>
          </div>
        )}

        {/* ── Tab G: Discharge ───────────────────────────────────── */}
        {tab === "discharge" && (
          <div className="enc-section surface-card">
            <div className="surface-card-heading"><div><p className="eyebrow">DISCHARGE</p><h2>Discharge Summary</h2></div></div>
            <div className="form-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
              <label>Discharge outcome
                <select value={dischOutcome} onChange={(e) => setDischOutcome(e.target.value)} disabled={readonly}>
                  <option value="">Select...</option>
                  <option value="home">Home</option>
                  <option value="referral">Referral</option>
                  <option value="transfer">Transfer</option>
                  <option value="against_advice">Against Medical Advice</option>
                  <option value="admitted">Admitted</option>
                </select>
              </label>
              <label>Discharge condition<input value={dischCondition} onChange={(e) => setDischCondition(e.target.value)} disabled={readonly} placeholder="Patient condition at discharge" /></label>
            </div>
            {(dischOutcome === "referral" || dischOutcome === "transfer") && (
              <div className="form-grid" style={{ gridTemplateColumns: "1fr", marginTop: 12 }}>
                <label>Destination<input value={dischDestination} onChange={(e) => setDischDestination(e.target.value)} disabled={readonly} placeholder="Facility / department being referred to" /></label>
              </div>
            )}
            <div className="form-grid" style={{ gridTemplateColumns: "1fr", marginTop: 12 }}>
              <label>Discharge reason<textarea value={dischReason} onChange={(e) => setDischReason(e.target.value)} rows={2} disabled={readonly} style={{ width: "100%", resize: "vertical" }} /></label>
              <label>Discharge notes<textarea value={dischargeNotes} onChange={(e) => setDischargeNotes(e.target.value)} rows={3} disabled={readonly} style={{ width: "100%", resize: "vertical" }} /></label>
              <label>Discharge instructions<textarea value={dischInstructions} onChange={(e) => setDischInstructions(e.target.value)} rows={3} disabled={readonly} style={{ width: "100%", resize: "vertical" }} placeholder="Instructions for the patient" /></label>
              <label>Warning signs<textarea value={warningSigns} onChange={(e) => setWarningSigns(e.target.value)} rows={2} disabled={readonly} style={{ width: "100%", resize: "vertical" }} placeholder="Signs that require immediate medical attention" /></label>
              <label>Medicine guidance<textarea value={medicineGuidance} onChange={(e) => setMedicineGuidance(e.target.value)} rows={2} disabled={readonly} style={{ width: "100%", resize: "vertical" }} placeholder="Instructions for medications" /></label>
            </div>
            <div className="form-grid" style={{ gridTemplateColumns: "1fr 1fr", marginTop: 12 }}>
              <label>Follow-up clinician<input value={followUpClinician} onChange={(e) => setFollowUpClinician(e.target.value)} disabled={readonly} /></label>
              <label>Follow-up department<input value={followUpDept} onChange={(e) => setFollowUpDept(e.target.value)} disabled={readonly} /></label>
            </div>
            {dischOutcome === "referral" && (
              <div className="form-grid" style={{ gridTemplateColumns: "1fr", marginTop: 12 }}>
                <label>Referral instructions<textarea value={referralInstructions} onChange={(e) => setReferralInstructions(e.target.value)} rows={2} disabled={readonly} style={{ width: "100%", resize: "vertical" }} /></label>
              </div>
            )}
            <div style={{ marginTop: 16 }}>
              <p className="eyebrow" style={{ marginBottom: 12 }}>DISCHARGE VITALS</p>
              <VitalsForm vitals={dischargeVitals} onChange={setDischargeVitals} readonly={readonly} />
            </div>
            {enc.status === "ready_for_discharge" && (
              <div style={{ marginTop: 20, paddingTop: 16, borderTop: "1px solid var(--line)" }}>
                <button className="button button-primary" type="button" disabled={busy} onClick={() => void completeDischarge()} style={{ background: "var(--leaf)" }}>{busy ? "Discharging..." : "Complete Discharge"}</button>
              </div>
            )}
          </div>
        )}

        {/* ── Tab H: Prescriptions ───────────────────────────────── */}
        {tab === "prescriptions" && (
          <div className="enc-section surface-card">
            <div className="surface-card-heading"><div><p className="eyebrow">DISCHARGE PRESCRIPTIONS</p><h2>Prescriptions ({prescriptions.length})</h2></div></div>
            {!prescriptionsLoaded && <div className="dashboard-empty" role="status"><strong>Loading prescriptions...</strong></div>}
            {prescriptionsLoaded && prescriptions.length === 0 && (
              <div className="dashboard-empty"><strong>No prescriptions</strong><span>Prescriptions linked to this encounter will appear here.</span></div>
            )}
            {prescriptions.length > 0 && (
              <div>
                {prescriptions.map((p) => (
                  <div key={p.id} style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr 1fr 1fr auto", gap: 8, padding: "10px 0", borderBottom: "1px solid var(--line)", alignItems: "center", fontSize: 13 }}>
                    <div><strong>{p.medication_name}</strong></div>
                    <div>{p.dosage ?? "-"}</div>
                    <div>{p.frequency ?? "-"}</div>
                    <div>{p.duration ?? "-"}</div>
                    <div><span style={{ fontSize: 11, padding: "1px 8px", borderRadius: 10, background: p.status === "active" ? "var(--leaf)" : "var(--line)", color: p.status === "active" ? "#fff" : "var(--fg)" }}>{p.status}</span></div>
                    <div style={{ fontSize: 11, color: "var(--muted)" }}>{fmtDateTime(p.prescribed_at)}</div>
                  </div>
                ))}
              </div>
            )}
            {enc && (
              <div style={{ marginTop: 16, fontSize: 12, color: "var(--muted)" }}>
                Prescriptions are created from the <a href={`/patients/${enc.patient_id}`} style={{ color: "var(--accent)" }}>patient record</a> and linked via encounter ID.
              </div>
            )}
          </div>
        )}

        {/* ── Tab I: Summary / Print ──────────────────────────────── */}
        {tab === "summary" && (
          <>
            <div className="enc-section surface-card enc-print-header" style={{ display: "none" }}>
              <h2 style={{ marginBottom: 4 }}>Clinical Encounter Summary</h2>
              <p>Patient: <strong>{enc.patient_name}</strong> {enc.mrn && `(MRN: ${enc.mrn})`} | Doctor: <strong>Dr. {enc.doctor_name}</strong> | Date: {fmtDateTime(enc.created_at)}</p>
            </div>
            <div className="enc-section surface-card">
              <div className="surface-card-heading"><div><p className="eyebrow">SUMMARY</p><h2>Encounter Summary</h2></div>
                <button className="button button-secondary" type="button" onClick={() => window.print()}>Print</button>
              </div>
              <SummarySection label="Status" value={statusLabel[enc.status] ?? enc.status} />
              <SummarySection label="Type" value={typeLabel(enc.encounter_type)} />
              {enc.arrival_mode && <SummarySection label="Arrival Mode" value={typeLabel(enc.arrival_mode)} />}
              {enc.arrival_datetime && <SummarySection label="Arrival Time" value={fmtDateTime(enc.arrival_datetime)} />}
              {enc.condition_on_arrival && <SummarySection label="Condition on Arrival" value={enc.condition_on_arrival} />}
              <SummarySection label="Chief Complaint" value={enc.chief_complaint} />
              <SummarySection label="HPI" value={enc.history_present_illness} />
              {enc.symptom_duration && <SummarySection label="Symptom Duration" value={enc.symptom_duration} />}
              <SummarySection label="Examination Findings" value={enc.examination_findings} />
              {(enc.gcs_eye != null || enc.gcs_verbal != null || enc.gcs_motor != null) && <SummarySection label="GCS" value={`E${enc.gcs_eye ?? "-"} V${enc.gcs_verbal ?? "-"} M${enc.gcs_motor ?? "-"} = ${(enc.gcs_eye ?? 0) + (enc.gcs_verbal ?? 0) + (enc.gcs_motor ?? 0)}`} />}
              {enc.pain_score != null && <SummarySection label="Pain Score" value={`${enc.pain_score}/10`} />}
              <SummarySection label="Diagnosis" value={enc.diagnosis} />
              <SummarySection label="Clinical Assessment" value={enc.clinical_assessment} />
              <SummarySection label="Investigations" value={enc.investigations} />
              <SummarySection label="Investigation Results" value={enc.investigation_results} />
              <SummarySection label="Treatment Plan" value={enc.treatment_plan} />
              <SummarySection label="Procedures" value={enc.procedures_performed} />
              {(enc.administered_treatments?.length ?? 0) > 0 && <SummarySection label="Administered Treatments" value={enc.administered_treatments!.map((t) => `${t.name}${t.dosage ? ` ${t.dosage}` : ""}${t.route ? ` (${t.route})` : ""}`).join("; ")} />}
              {(enc.administered_procedures?.length ?? 0) > 0 && <SummarySection label="Administered Procedures" value={enc.administered_procedures!.map((p) => `${p.name}${p.performer ? ` by ${p.performer}` : ""}`).join("; ")} />}
              <SummarySection label="Treatment Response" value={enc.treatment_response} />
              <SummarySection label="Adverse Reactions" value={enc.adverse_reactions} />
              {(enc.medications?.length ?? 0) > 0 && <SummarySection label="Medications" value={enc.medications!.map((m) => `${m.name}${m.dosage ? ` ${m.dosage}` : ""}${m.frequency ? ` ${m.frequency}` : ""}${m.duration ? ` x ${m.duration}` : ""}`).join("; ")} />}
              <SummarySection label="Discharge Outcome" value={enc.discharge_outcome ? typeLabel(enc.discharge_outcome) : null} />
              <SummarySection label="Discharge Condition" value={enc.discharge_condition} />
              <SummarySection label="Discharge Notes" value={enc.discharge_notes} />
              <SummarySection label="Discharge Instructions" value={enc.discharge_instructions} />
              <SummarySection label="Warning Signs" value={enc.warning_signs} />
              <SummarySection label="Medicine Guidance" value={enc.medicine_guidance} />
              <SummarySection label="Follow-up" value={[enc.follow_up_date && `Date: ${fmtDate(enc.follow_up_date)}`, enc.follow_up_instructions, enc.follow_up_clinician && `Clinician: ${enc.follow_up_clinician}`, enc.follow_up_department && `Dept: ${enc.follow_up_department}`].filter(Boolean).join(" | ") || null} />
              {enc.internal_notes && <div style={{ marginTop: 12, padding: "8px 12px", background: "var(--bg-alt, rgba(0,0,0,0.03))", borderRadius: 6, fontStyle: "italic", fontSize: 13 }}><span className="eyebrow">INTERNAL NOTES (NOT PRINTED)</span><p>{enc.internal_notes}</p></div>}
            </div>

            {/* Amendment history */}
            {(enc.amendment_history?.length ?? 0) > 0 && (
              <div className="enc-section surface-card" style={{ marginTop: 16 }}>
                <div className="surface-card-heading"><div><p className="eyebrow">AUDIT</p><h2>Amendment History</h2></div></div>
                {enc.amendment_history!.map((a, idx) => (
                  <div key={idx} style={{ padding: "8px 0", borderBottom: "1px solid var(--line)", fontSize: 13 }}>
                    <strong>{AMENDABLE_FIELDS.find((f) => f.value === a.field)?.label ?? a.field}</strong> amended on {fmtDateTime(a.amended_at)}
                    <p style={{ color: "var(--muted)", marginTop: 2 }}>Reason: {a.reason}</p>
                    <p style={{ marginTop: 2 }}>New value: {a.new_value.length > 200 ? a.new_value.slice(0, 200) + "..." : a.new_value}</p>
                  </div>
                ))}
              </div>
            )}

            {/* Amend form */}
            {(enc.status === "discharged" || enc.status === "finalized") && (
              <div className="enc-section surface-card" style={{ marginTop: 16 }}>
                <div className="surface-card-heading"><div><p className="eyebrow">CORRECTION</p><h2>Amend Record</h2></div></div>
                <div className="form-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
                  <label>Field to amend
                    <select value={amendField} onChange={(e) => { setAmendField(e.target.value); setAmendNewValue(""); }}>
                      <option value="">Select field...</option>
                      {AMENDABLE_FIELDS.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
                    </select>
                  </label>
                  {amendField && (
                    <div><span className="eyebrow">CURRENT VALUE</span><p style={{ fontSize: 13, marginTop: 4, maxHeight: 60, overflow: "auto" }}>{((enc as Record<string, unknown>)[amendField] as string) || "(empty)"}</p></div>
                  )}
                </div>
                {amendField && (
                  <div className="form-grid" style={{ gridTemplateColumns: "1fr", marginTop: 12 }}>
                    <label>New value<textarea value={amendNewValue} onChange={(e) => setAmendNewValue(e.target.value)} rows={3} style={{ width: "100%", resize: "vertical" }} /></label>
                    <label>Reason for amendment<textarea value={amendReason} onChange={(e) => setAmendReason(e.target.value)} rows={2} style={{ width: "100%", resize: "vertical" }} placeholder="Required: explain why this amendment is needed" /></label>
                    <div><button className="button button-secondary" type="button" disabled={busy || !amendNewValue || !amendReason} onClick={() => void submitAmendment()}>{busy ? "Submitting..." : "Submit Amendment"}</button></div>
                  </div>
                )}
              </div>
            )}
          </>
        )}

        {/* Save button (not on discharge or summary tabs) */}
        {!readonly && tab !== "summary" && tab !== "discharge" && (
          <div className="form-actions" style={{ marginTop: 16 }}>
            <button className="button button-primary" type="submit" disabled={busy}>{busy ? "Saving..." : "Save encounter"}</button>
          </div>
        )}
        {/* Discharge tab: also allow saving without completing discharge */}
        {!readonly && tab === "discharge" && enc.status !== "ready_for_discharge" && (
          <div className="form-actions" style={{ marginTop: 16 }}>
            <button className="button button-primary" type="submit" disabled={busy}>{busy ? "Saving..." : "Save encounter"}</button>
          </div>
        )}
      </form>
    </section>
  );
}

/* ── GCS Calculator ────────────────────────────────────────────────── */
const GCS_EYE = [{ v: 4, l: "4 - Spontaneous" }, { v: 3, l: "3 - To voice" }, { v: 2, l: "2 - To pain" }, { v: 1, l: "1 - None" }];
const GCS_VERBAL = [{ v: 5, l: "5 - Oriented" }, { v: 4, l: "4 - Confused" }, { v: 3, l: "3 - Inappropriate" }, { v: 2, l: "2 - Incomprehensible" }, { v: 1, l: "1 - None" }];
const GCS_MOTOR = [{ v: 6, l: "6 - Obeys commands" }, { v: 5, l: "5 - Localizes pain" }, { v: 4, l: "4 - Withdrawal" }, { v: 3, l: "3 - Abnormal flexion" }, { v: 2, l: "2 - Extension" }, { v: 1, l: "1 - None" }];

function GCSCalculator({ eye, verbal, motor, onChange, readonly }: { eye: number | null; verbal: number | null; motor: number | null; onChange: (field: string, value: number | null) => void; readonly: boolean }) {
  const total = (eye ?? 0) + (verbal ?? 0) + (motor ?? 0);
  const hasAll = eye != null && verbal != null && motor != null;
  const classification = !hasAll ? "" : total >= 13 ? "Mild" : total >= 9 ? "Moderate" : "Severe";
  const classColor = classification === "Mild" ? "var(--leaf)" : classification === "Moderate" ? "#e0a458" : classification === "Severe" ? "var(--coral)" : "var(--muted)";

  return (
    <div style={{ marginTop: 16, padding: "12px 16px", background: "var(--bg-alt, rgba(0,0,0,0.03))", borderRadius: 8 }}>
      <p className="eyebrow" style={{ marginBottom: 8 }}>GLASGOW COMA SCALE (GCS)</p>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr auto", gap: 12, alignItems: "end" }}>
        <label style={{ fontSize: 12 }}>Eye Response (E)
          <select value={eye ?? ""} onChange={(e) => onChange("eye", e.target.value === "" ? null : parseInt(e.target.value, 10))} disabled={readonly}>
            <option value="">-</option>
            {GCS_EYE.map((o) => <option key={o.v} value={o.v}>{o.l}</option>)}
          </select>
        </label>
        <label style={{ fontSize: 12 }}>Verbal Response (V)
          <select value={verbal ?? ""} onChange={(e) => onChange("verbal", e.target.value === "" ? null : parseInt(e.target.value, 10))} disabled={readonly}>
            <option value="">-</option>
            {GCS_VERBAL.map((o) => <option key={o.v} value={o.v}>{o.l}</option>)}
          </select>
        </label>
        <label style={{ fontSize: 12 }}>Motor Response (M)
          <select value={motor ?? ""} onChange={(e) => onChange("motor", e.target.value === "" ? null : parseInt(e.target.value, 10))} disabled={readonly}>
            <option value="">-</option>
            {GCS_MOTOR.map((o) => <option key={o.v} value={o.v}>{o.l}</option>)}
          </select>
        </label>
        <div style={{ textAlign: "center", minWidth: 80 }}>
          <p style={{ fontSize: 11, color: "var(--muted)" }}>TOTAL</p>
          <p style={{ fontSize: 22, fontWeight: 700 }}>{hasAll ? total : "-"}</p>
          {classification && <p style={{ fontSize: 11, fontWeight: 600, color: classColor }}>{classification}</p>}
        </div>
      </div>
    </div>
  );
}

/* ── BMI Display ───────────────────────────────────────────────────── */
function BMIDisplay({ vitals, label }: { vitals: Vitals; label: string }) {
  if (!vitals.weight_kg || !vitals.height_cm) return null;
  const bmi = vitals.weight_kg / Math.pow(vitals.height_cm / 100, 2);
  const bmiStr = bmi.toFixed(1);
  const category = bmi < 18.5 ? "Underweight" : bmi < 25 ? "Normal" : bmi < 30 ? "Overweight" : "Obese";
  const color = category === "Normal" ? "var(--leaf)" : category === "Underweight" ? "#5886b4" : category === "Overweight" ? "#e0a458" : "var(--coral)";
  return (
    <div style={{ marginTop: 10, padding: "6px 12px", background: "var(--bg-alt, rgba(0,0,0,0.03))", borderRadius: 6, display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}>
      <span style={{ fontWeight: 600 }}>{label} BMI:</span>
      <span style={{ fontWeight: 700, color }}>{bmiStr}</span>
      <span style={{ color, fontSize: 11 }}>({category})</span>
    </div>
  );
}

/* ── Summary Section ───────────────────────────────────────────────── */
function SummarySection({ label, value }: { label: string; value: string | null | undefined }) {
  if (!value) return null;
  return (
    <div style={{ padding: "6px 0", borderBottom: "1px solid var(--line)" }}>
      <span className="eyebrow">{label.toUpperCase()}</span>
      <p style={{ fontSize: 13, marginTop: 2, whiteSpace: "pre-wrap" }}>{value}</p>
    </div>
  );
}

/* ── Vitals Form ───────────────────────────────────────────────────── */
function VitalsForm({ vitals, onChange, readonly }: { vitals: Vitals; onChange: (v: Vitals) => void; readonly: boolean }) {
  const set = (field: keyof Vitals, val: string) => {
    onChange({ ...vitals, [field]: val === "" ? undefined : (["pulse", "respiratory_rate", "oxygen_saturation"].includes(field) ? parseInt(val, 10) : ["temperature", "weight_kg", "height_cm"].includes(field) ? parseFloat(val) : val) });
  };
  return (
    <div className="form-grid">
      <label>Blood pressure<input value={vitals.blood_pressure ?? ""} onChange={(e) => set("blood_pressure", e.target.value)} disabled={readonly} placeholder="120/80" /></label>
      <label>Pulse (bpm)<input type="number" value={vitals.pulse ?? ""} onChange={(e) => set("pulse", e.target.value)} disabled={readonly} /></label>
      <label>Temperature (&deg;C)<input type="number" step="0.1" value={vitals.temperature ?? ""} onChange={(e) => set("temperature", e.target.value)} disabled={readonly} /></label>
      <label>Respiratory rate<input type="number" value={vitals.respiratory_rate ?? ""} onChange={(e) => set("respiratory_rate", e.target.value)} disabled={readonly} /></label>
      <label>SpO2 (%)<input type="number" value={vitals.oxygen_saturation ?? ""} onChange={(e) => set("oxygen_saturation", e.target.value)} disabled={readonly} /></label>
      <label>Weight (kg)<input type="number" step="0.1" value={vitals.weight_kg ?? ""} onChange={(e) => set("weight_kg", e.target.value)} disabled={readonly} /></label>
      <label>Height (cm)<input type="number" step="0.1" value={vitals.height_cm ?? ""} onChange={(e) => set("height_cm", e.target.value)} disabled={readonly} /></label>
      <label>Notes<input value={vitals.notes ?? ""} onChange={(e) => set("notes", e.target.value)} disabled={readonly} /></label>
    </div>
  );
}
