"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { api, errorMessage, writeHeaders } from "../../_lib/client";
import { useToast } from "../../_lib/toast";
import { useConfirm } from "../../_lib/confirm";

/* ── Types ─────────────────────────────────────────────────────────── */
type Vitals = { blood_pressure?: string; pulse?: number; temperature?: number; respiratory_rate?: number; oxygen_saturation?: number; weight_kg?: number; height_cm?: number; notes?: string };
type Medication = { name: string; dosage?: string; route?: string; frequency?: string; duration?: string; notes?: string; inventory_product_id?: string; unit_price_minor?: number; currency?: string };
type AdministeredTreatment = { name: string; dosage?: string; route?: string; administered_at?: string; administered_by?: string; response?: string; notes?: string; service_id?: string; inventory_product_id?: string; unit_price_minor?: number; currency?: string; quantity?: number };
type AdministeredProcedure = { name: string; performed_at?: string; performer?: string; findings?: string; notes?: string; service_id?: string; unit_price_minor?: number; currency?: string };
type CatalogService = { id: string; name: string; category: string; price_mode: string; amount_minor: number | null; currency: string | null; status: string };
type InventoryProduct = { id: string; name: string; product_type: string; unit: string; status: string };
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
  token_number: number | null;
  doctor_user_id: string | null;
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

function formatPrice(amountMinor: number | null | undefined, cur?: string | null, priceMode?: string): string {
  if (amountMinor == null) return "";
  const amount = (amountMinor / 100).toLocaleString();
  const c = cur ?? "PKR";
  if (priceMode === "starting_at") return `from ${c} ${amount}`;
  if (priceMode === "contact") return "Price on request";
  return `${c} ${amount}`;
}

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

type Tab = "arrival" | "patient" | "assessment" | "treatment" | "medications" | "vitals" | "discharge" | "summary";
const TABS: Tab[] = ["arrival", "patient", "assessment", "treatment", "medications", "vitals", "discharge", "summary"];

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
  const [currentUserId, setCurrentUserId] = useState<string | null>(null);

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

  // Catalog pickers
  const [catalogServices, setCatalogServices] = useState<CatalogService[]>([]);
  const [inventoryProducts, setInventoryProducts] = useState<InventoryProduct[]>([]);
  const [catalogLoadFailed, setCatalogLoadFailed] = useState(false);
  const [pickerOpen, setPickerOpen] = useState<string | null>(null);
  const [pickerSearch, setPickerSearch] = useState("");

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

  // Amendment
  const [amendField, setAmendField] = useState("");
  const [amendNewValue, setAmendNewValue] = useState("");
  const [amendReason, setAmendReason] = useState("");

  // Invoice
  const [invoiceData, setInvoiceData] = useState<{ id: string; invoice_number: string; status: string; total_minor: number; currency: string; paid_minor: number } | null>(null);
  const [invoiceLoading, setInvoiceLoading] = useState(false);
  const [showInvoicePreview, setShowInvoicePreview] = useState(false);

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
  useEffect(() => {
    void api<{ user_id: string }>("/api/v1/auth/me").then((s) => { if (s?.user_id) setCurrentUserId(s.user_id); }).catch(() => {});
    void api<CatalogService[]>("/api/v1/services?limit=100").then((d) => setCatalogServices((d ?? []).filter((s) => s.status === "active"))).catch(() => setCatalogLoadFailed(true));
    void api<InventoryProduct[]>("/api/v1/inventory/products?limit=100").then((d) => setInventoryProducts((d ?? []).filter((p) => p.status === "active"))).catch(() => setCatalogLoadFailed(true));
  }, []);

  useEffect(() => {
    if (!encounterId) return;
    setInvoiceLoading(true);
    void api<{ id: string; invoice_number: string; status: string; total_minor: number; currency: string; paid_minor: number }>(`/api/v1/encounters/${encounterId}/invoice`)
      .then((d) => { if (d) setInvoiceData(d); })
      .catch(() => {})
      .finally(() => setInvoiceLoading(false));
  }, [encounterId]);

  async function generateInvoice() {
    if (!enc) return;
    setBusy(true);
    try {
      const currency = treatments.find((t) => t.currency)?.currency ?? adminProcedures.find((p) => p.currency)?.currency ?? "PKR";
      const res = await api<{ id: string; invoice_number: string; status: string; total_minor: number; currency: string }>(`/api/v1/encounters/${encounterId}/generate-invoice`, { method: "POST", headers: writeHeaders(), body: JSON.stringify({ currency, discount_minor: 0 }) });
      if (res) {
        setInvoiceData({ ...res, paid_minor: 0 });
        setShowInvoicePreview(false);
        toast.success(`Invoice ${res.invoice_number} created successfully.`);
      }
    } catch (reason) {
      toast.error(errorMessage(reason, "Could not generate invoice."));
    } finally { setBusy(false); }
  }

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
      // Administered — filter out incomplete rows and convert empty optional strings to null
      const cleanTreatments = treatments
        .filter((t) => t.name.trim())
        .map((t) => ({ name: t.name.trim(), dosage: t.dosage || null, route: t.route || null, administered_at: t.administered_at || null, administered_by: t.administered_by || null, response: t.response || null, notes: t.notes || null, service_id: t.service_id || null, inventory_product_id: t.inventory_product_id || null, unit_price_minor: t.unit_price_minor ?? null, currency: t.currency || null, quantity: t.quantity ?? null }));
      const cleanProcedures = adminProcedures
        .filter((p) => p.name.trim())
        .map((p) => ({ name: p.name.trim(), performed_at: p.performed_at || null, performer: p.performer || null, findings: p.findings || null, notes: p.notes || null, service_id: p.service_id || null, unit_price_minor: p.unit_price_minor ?? null, currency: p.currency || null }));
      if (JSON.stringify(cleanTreatments) !== JSON.stringify((enc.administered_treatments ?? []).map((t) => ({ name: t.name, dosage: t.dosage || null, route: t.route || null, administered_at: t.administered_at || null, administered_by: t.administered_by || null, response: t.response || null, notes: t.notes || null, service_id: t.service_id || null, inventory_product_id: t.inventory_product_id || null, unit_price_minor: t.unit_price_minor ?? null, currency: t.currency || null, quantity: t.quantity ?? null })))) {
        body.administered_treatments = cleanTreatments;
      }
      if (JSON.stringify(cleanProcedures) !== JSON.stringify((enc.administered_procedures ?? []).map((p) => ({ name: p.name, performed_at: p.performed_at || null, performer: p.performer || null, findings: p.findings || null, notes: p.notes || null, service_id: p.service_id || null, unit_price_minor: p.unit_price_minor ?? null, currency: p.currency || null })))) {
        body.administered_procedures = cleanProcedures;
      }
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
      // Meds & vitals — filter out incomplete medication rows
      const cleanMeds = meds
        .filter((m) => m.name.trim())
        .map((m) => ({ name: m.name.trim(), dosage: m.dosage || null, route: m.route || null, frequency: m.frequency || null, duration: m.duration || null, notes: m.notes || null, inventory_product_id: m.inventory_product_id || null, unit_price_minor: m.unit_price_minor ?? null, currency: m.currency || null }));
      if (JSON.stringify(cleanMeds) !== JSON.stringify((enc.medications ?? []).map((m) => ({ name: m.name, dosage: m.dosage || null, route: m.route || null, frequency: m.frequency || null, duration: m.duration || null, notes: m.notes || null, inventory_product_id: m.inventory_product_id || null, unit_price_minor: m.unit_price_minor ?? null, currency: m.currency || null })))) {
        body.medications = cleanMeds;
      }
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

  /* ── Medication helpers ───────────────────────────────────────── */
  function addMed() { setMeds([...meds, { name: "", dosage: "", route: "oral", frequency: "", duration: "" }]); }
  function updateMed(idx: number, field: keyof Medication, val: string) { setMeds(meds.map((m, i) => i === idx ? { ...m, [field]: val } : m)); }
  function removeMed(idx: number) { setMeds(meds.filter((_, i) => i !== idx)); }

  /* ── Treatment helpers ────────────────────────────────────────── */
  function addTreatment() { setTreatments([...treatments, { name: "", dosage: "", route: "", administered_at: "", administered_by: "", response: "", notes: "" }]); }
  function updateTreatment(idx: number, field: keyof AdministeredTreatment, val: string) { setTreatments(treatments.map((t, i) => i === idx ? { ...t, [field]: field === "quantity" ? Math.max(1, parseInt(val) || 1) : val } : t)); }
  function removeTreatment(idx: number) { setTreatments(treatments.filter((_, i) => i !== idx)); }

  function addProcedure() { setAdminProcedures([...adminProcedures, { name: "", performed_at: "", performer: "", findings: "", notes: "" }]); }
  function updateProcedure(idx: number, field: keyof AdministeredProcedure, val: string) { setAdminProcedures(adminProcedures.map((p, i) => i === idx ? { ...p, [field]: val } : p)); }
  function removeProcedure(idx: number) { setAdminProcedures(adminProcedures.filter((_, i) => i !== idx)); }

  /* ── Catalog picker helpers ──────────────────────────────────── */
  function addTreatmentFromService(svc: CatalogService) {
    const svcRow: AdministeredTreatment = { name: svc.name, service_id: svc.id, unit_price_minor: svc.amount_minor ?? undefined, currency: svc.currency ?? undefined, quantity: 1, dosage: "", route: "", administered_at: "", administered_by: "", response: "", notes: "" };
    setTreatments((prev) => [...prev, svcRow]);
    setPickerOpen(null); setPickerSearch("");
    void api<{ inventory_product_id: string; product_name: string; default_quantity: number; unit: string }[]>(`/api/v1/services/${svc.id}/materials`).then((mats) => {
      if (!mats?.length) return;
      const newRows: AdministeredTreatment[] = mats.map((m) => ({ name: `${m.product_name} (for ${svc.name})`, inventory_product_id: m.inventory_product_id, quantity: m.default_quantity, dosage: "", route: "", administered_at: "", administered_by: "", response: "", notes: "" }));
      setTreatments((prev) => [...prev, ...newRows]);
      toast.success(`Added ${mats.length} material${mats.length > 1 ? "s" : ""} for ${svc.name}.`);
    }).catch(() => {});
  }
  function addTreatmentFromInventory(prod: InventoryProduct) {
    setTreatments([...treatments, { name: prod.name, inventory_product_id: prod.id, dosage: "", route: "", administered_at: "", administered_by: "", response: "", notes: "" }]);
    setPickerOpen(null); setPickerSearch("");
  }
  function addProcedureFromService(svc: CatalogService) {
    setAdminProcedures([...adminProcedures, { name: svc.name, service_id: svc.id, unit_price_minor: svc.amount_minor ?? undefined, currency: svc.currency ?? undefined, performed_at: "", performer: "", findings: "", notes: "" }]);
    setPickerOpen(null); setPickerSearch("");
  }
  function addMedFromInventory(prod: InventoryProduct) {
    setMeds([...meds, { name: prod.name, inventory_product_id: prod.id, dosage: "", route: "oral", frequency: "", duration: "" }]);
    setPickerOpen(null); setPickerSearch("");
  }
  function togglePicker(key: string) {
    setPickerOpen(pickerOpen === key ? null : key);
    setPickerSearch("");
  }

  const pageRef = useRef<HTMLElement>(null);

  /* ── Loading / Error ──────────────────────────────────────────── */
  if (loading) return <main className="dash-content"><div className="dashboard-empty" role="status"><strong>Loading encounter...</strong></div></main>;
  if (error || !enc) return <main className="dash-content"><div className="workspace-alert" role="alert"><strong>{error ?? "Encounter not found."}</strong></div><Link className="button button-secondary" href="/encounters">Back</Link></main>;

  const readonly = enc.status === "discharged" || enc.status === "finalized";
  const isDraft = enc.status === "draft";
  const lockedTabs: Set<Tab> = new Set();
  const arrivalLocked = !isDraft && !readonly;

  /* ── Render ───────────────────────────────────────────────────── */
  return (
    <main className="dash-content" ref={pageRef}>
      {/* Header */}
      <div className="dash-topline">
        <div>
          <p className="eyebrow"><Link href="/encounters" className="enc-d-link-muted">ENCOUNTERS</Link> &middot; {typeLabel(enc.encounter_type).toUpperCase()}</p>
          <h1><Link href={`/patients/${enc.patient_id}`} className="enc-d-link-inherit">{enc.patient_name}</Link></h1>
          <p className="enc-d-meta">Dr. {enc.doctor_name}{enc.doctor_specialty && ` · ${enc.doctor_specialty}`}{enc.branch_name && ` · ${enc.branch_name}`}</p>
        </div>
        <div className="header-actions">
          <span className="enc-detail-status-badge" style={{ background: statusColor[enc.status] ?? "var(--line)" }}>{statusLabel[enc.status] ?? typeLabel(enc.status)}</span>
          {enc.status === "draft" && <button className="button button-secondary" type="button" disabled={busy} onClick={() => void changeStatus("in_progress")}>Begin Assessment</button>}
          {enc.status === "in_progress" && <button className="button button-secondary" type="button" disabled={busy} onClick={() => void changeStatus("ready_for_discharge")}>Ready for Discharge</button>}
          {enc.status === "discharged" && <button className="button button-primary" type="button" disabled={busy} onClick={() => void changeStatus("finalized")}>Finalize</button>}
          {(enc.status === "discharged" || enc.status === "finalized") && !invoiceLoading && !invoiceData && (
            <button className="button button-primary enc-d-sm-btn" type="button" disabled={busy} onClick={() => setShowInvoicePreview(true)}>Generate Invoice</button>
          )}
          {invoiceData && (
            <Link className="button button-secondary enc-d-inv-link" href={`/billing?invoice=${invoiceData.id}`}>
              <span className="enc-d-inv-badge" style={{ background: invoiceData.status === "paid" ? "var(--leaf)" : invoiceData.status === "void" ? "var(--coral)" : "var(--accent)" }}>{invoiceData.status.toUpperCase()}</span>
              {invoiceData.invoice_number}
            </Link>
          )}
          {enc.mrn && <span className="muted-mono">MRN: {enc.mrn}</span>}
        </div>
      </div>

      {/* Summary bar */}
      <div className="billing-summary">
        <div><span className="eyebrow">CREATED</span><strong className="enc-d-date-val">{fmtDateTime(enc.created_at)}</strong></div>
        {enc.discharge_datetime && <div><span className="eyebrow">DISCHARGED</span><strong className="enc-d-date-val">{fmtDateTime(enc.discharge_datetime)}</strong></div>}
        {enc.finalized_at && <div><span className="eyebrow">FINALIZED</span><strong className="enc-d-date-val">{fmtDateTime(enc.finalized_at)}</strong></div>}
        <div><span className="eyebrow">TYPE</span><strong className="enc-d-date-val">{typeLabel(enc.encounter_type)}</strong></div>
        {(() => {
          const tTotal = (enc.administered_treatments ?? []).reduce((s, t) => s + (t.unit_price_minor ?? 0) * (t.quantity ?? 1), 0);
          const pTotal = (enc.administered_procedures ?? []).reduce((s, p) => s + (p.unit_price_minor ?? 0), 0);
          const grand = tTotal + pTotal;
          if (grand <= 0) return null;
          const cur = (enc.administered_treatments ?? []).find((t) => t.currency)?.currency ?? (enc.administered_procedures ?? []).find((p) => p.currency)?.currency ?? "PKR";
          return <div><span className="eyebrow">CHARGES</span><strong className="enc-d-charges-val">{formatPrice(grand, cur)}</strong></div>;
        })()}
      </div>

      {/* Tabs */}
      <div className="pipeline-toolbar">
        <div className="pipeline-tabs" role="tablist">
          {TABS.map((t) => (
            <button key={t} className={tab === t ? "active" : ""} disabled={lockedTabs.has(t)} onClick={() => { if (!lockedTabs.has(t)) setTab(t); }}>{typeLabel(t)}</button>
          ))}
        </div>
      </div>

      {/* Invoice preview confirmation */}
      {showInvoicePreview && enc && (() => {
        const lines: { name: string; qty: number; price: number; currency: string }[] = [];
        for (const t of enc.administered_treatments ?? []) {
          if (t.unit_price_minor && t.unit_price_minor > 0) lines.push({ name: t.name, qty: t.quantity ?? 1, price: t.unit_price_minor, currency: t.currency ?? "PKR" });
        }
        for (const p of enc.administered_procedures ?? []) {
          if (p.unit_price_minor && p.unit_price_minor > 0) lines.push({ name: p.name, qty: 1, price: p.unit_price_minor, currency: p.currency ?? "PKR" });
        }
        const total = lines.reduce((s, l) => s + l.price * l.qty, 0);
        const cur = lines[0]?.currency ?? "PKR";
        return (
          <div className="enc-detail-modal-overlay" onClick={() => setShowInvoicePreview(false)}>
            <div className="surface-card enc-detail-modal-card" onClick={(e) => e.stopPropagation()}>
              <h2 className="enc-d-modal-title">Generate Invoice</h2>
              <p className="enc-d-modal-desc">Review line items from this encounter before generating the invoice.</p>
              {lines.length === 0 ? (
                <p className="enc-d-modal-empty">No priced treatments or procedures found. Add prices to treatments first.</p>
              ) : (
                <table className="enc-d-preview-table">
                  <thead><tr><th>Item</th><th>Qty</th><th>Amount</th></tr></thead>
                  <tbody>
                    {lines.map((l, i) => (
                      <tr key={i}>
                        <td>{l.name}</td>
                        <td>{l.qty}</td>
                        <td>{formatPrice(l.price * l.qty, l.currency)}</td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot><tr><td colSpan={2}>Total</td><td>{formatPrice(total, cur)}</td></tr></tfoot>
                </table>
              )}
              <div className="enc-d-modal-actions">
                <button className="button button-secondary" type="button" onClick={() => setShowInvoicePreview(false)}>Cancel</button>
                {lines.length > 0 && <button className="button button-primary" type="button" disabled={busy} onClick={() => void generateInvoice()}>{busy ? "Generating..." : "Confirm & Generate"}</button>}
              </div>
            </div>
          </div>
        );
      })()}

      <form onSubmit={(e) => void save(e)}>

        {/* ── Tab A: Arrival ─────────────────────────────────────── */}
        {tab === "arrival" && (
          <div className="enc-section surface-card">
            <div className="surface-card-heading"><div><p className="eyebrow">ARRIVAL</p><h2>Arrival Information</h2></div>{arrivalLocked && <span className="enc-d-locked-hint">Locked after assessment started</span>}</div>
            <div className="form-grid enc-detail-grid-2col">
              <label>Arrival mode
                <select value={arrivalMode} onChange={(e) => setArrivalMode(e.target.value)} disabled={readonly || arrivalLocked}>
                  <option value="">Select...</option>
                  <option value="walk_in">Walk-in</option>
                  <option value="ambulance">Ambulance</option>
                  <option value="referral">Referral</option>
                  <option value="transfer">Transfer</option>
                  <option value="self">Self</option>
                </select>
              </label>
              <label>Arrival date/time<input type="datetime-local" value={arrivalDatetime} onChange={(e) => setArrivalDatetime(e.target.value)} disabled={readonly || arrivalLocked} /></label>
              <label>Attendant name<input value={attendantName} onChange={(e) => setAttendantName(e.target.value)} disabled={readonly || arrivalLocked} placeholder="Name of accompanying person" /></label>
              <label>Attendant phone<input value={attendantPhone} onChange={(e) => setAttendantPhone(e.target.value)} disabled={readonly || arrivalLocked} placeholder="Phone number" /></label>
            </div>
            <div className="form-grid enc-detail-grid-1col-mt">
              <label>Condition on arrival<textarea value={conditionOnArrival} onChange={(e) => setConditionOnArrival(e.target.value)} rows={2} disabled={readonly || arrivalLocked} className="enc-detail-textarea" placeholder="Patient's condition when they arrived" /></label>
            </div>
            <div className="enc-d-section-gap">
              <p className="eyebrow enc-d-eyebrow-tight">ARRIVAL VITALS</p>
              <VitalsForm vitals={arrivalVitals} onChange={setArrivalVitals} readonly={readonly || arrivalLocked} />
            </div>
          </div>
        )}

        {/* ── Tab B: Patient Summary ─────────────────────────────── */}
        {tab === "patient" && (
          <div className="enc-section surface-card">
            <div className="surface-card-heading"><div><p className="eyebrow">PATIENT</p><h2>Patient Summary</h2></div></div>
            <div className="enc-detail-info-box">
              <div><span className="eyebrow">NAME</span><p className="enc-d-field-name">{enc.patient_name}</p></div>
              <div><span className="eyebrow">MRN</span><p>{enc.mrn ?? "N/A"}</p></div>
              <div><span className="eyebrow">DATE OF BIRTH</span><p>{enc.patient_dob ? `${fmtDate(enc.patient_dob)} (${computeAge(enc.patient_dob)})` : "N/A"}</p></div>
              <div><span className="eyebrow">ALLERGIES (PATIENT RECORD)</span><p>{enc.patient_allergies || "None on file"}</p></div>
              <div><span className="eyebrow">CONTRAINDICATIONS</span><p>{enc.patient_contraindications || "None on file"}</p></div>
              <div><span className="eyebrow">EMERGENCY CONTACT</span><p>{enc.emergency_contact_name ? `${enc.emergency_contact_name}${enc.emergency_contact_relation ? ` (${enc.emergency_contact_relation})` : ""} ${enc.emergency_contact_phone ?? ""}` : "None on file"}</p></div>
            </div>
            <div className="form-grid enc-detail-grid-2col">
              <label>Allergy status
                <select value={allergyStatus} onChange={(e) => setAllergyStatus(e.target.value)} disabled={readonly}>
                  <option value="unknown">Unknown</option>
                  <option value="none_known">No Known Allergies (NKA)</option>
                  <option value="has_allergies">Has Allergies</option>
                </select>
              </label>
              <label>Known allergies (this encounter)<input value={knownAllergies} onChange={(e) => setKnownAllergies(e.target.value)} disabled={readonly} placeholder="List known allergies" /></label>
            </div>
            <div className="form-grid enc-detail-grid-1col-mt">
              <label>Medical history<textarea value={medicalHistory} onChange={(e) => setMedicalHistory(e.target.value)} rows={3} disabled={readonly} className="enc-detail-textarea" placeholder="Relevant past medical history" /></label>
              <label>Current medications<textarea value={currentMedsText} onChange={(e) => setCurrentMedsText(e.target.value)} rows={2} disabled={readonly} className="enc-detail-textarea" placeholder="Medications patient is currently taking" /></label>
            </div>
          </div>
        )}

        {/* ── Tab C: Assessment ──────────────────────────────────── */}
        {tab === "assessment" && (
          <div className="enc-section surface-card">
            <div className="surface-card-heading"><div><p className="eyebrow">CLINICAL</p><h2>Assessment</h2></div></div>
            <div className="form-grid enc-detail-grid-1col">
              <label>Chief complaint<textarea value={complaint} onChange={(e) => setComplaint(e.target.value)} rows={2} disabled={readonly} className="enc-detail-textarea" /></label>
              <label>History of present illness<textarea value={hpi} onChange={(e) => setHpi(e.target.value)} rows={3} disabled={readonly} className="enc-detail-textarea" /></label>
              <div className="form-grid enc-detail-grid-2col">
                <label>Symptom duration<input value={symptomDuration} onChange={(e) => setSymptomDuration(e.target.value)} disabled={readonly} placeholder="e.g. 3 days" /></label>
                <label>Pain score (0-10)
                  <div className="enc-detail-btn-group">
                    <input type="number" min={0} max={10} value={painScore ?? ""} onChange={(e) => setPainScore(e.target.value === "" ? null : parseInt(e.target.value, 10))} disabled={readonly} className="enc-d-pain-input" />
                    {painScore != null && <span className="enc-d-xs-btn" style={{ fontWeight: 600, color: painScore <= 3 ? "var(--leaf)" : painScore <= 6 ? "#e0a458" : "var(--coral)" }}>{painScore <= 3 ? "Mild" : painScore <= 6 ? "Moderate" : "Severe"}</span>}
                  </div>
                </label>
              </div>
              <label>Examination findings<textarea value={exam} onChange={(e) => setExam(e.target.value)} rows={3} disabled={readonly} className="enc-detail-textarea" /></label>
            </div>
            <GCSCalculator eye={gcsEye} verbal={gcsVerbal} motor={gcsMotor} onChange={(f, v) => { if (f === "eye") setGcsEye(v); else if (f === "verbal") setGcsVerbal(v); else setGcsMotor(v); }} readonly={readonly} />
            <div className="form-grid enc-detail-grid-1col-mt">
              <label>Investigations<textarea value={investigations} onChange={(e) => setInvestigations(e.target.value)} rows={2} disabled={readonly} className="enc-detail-textarea" /></label>
              <label>Investigation results<textarea value={investigationResults} onChange={(e) => setInvestigationResults(e.target.value)} rows={2} disabled={readonly} className="enc-detail-textarea" /></label>
              <label>Diagnosis<textarea value={diagnosis} onChange={(e) => setDiagnosis(e.target.value)} rows={2} disabled={readonly} className="enc-detail-textarea" /></label>
              <label>Clinical assessment<textarea value={clinicalAssessment} onChange={(e) => setClinicalAssessment(e.target.value)} rows={2} disabled={readonly} className="enc-detail-textarea" /></label>
              <label>Treatment plan<textarea value={treatmentPlan} onChange={(e) => setTreatmentPlan(e.target.value)} rows={2} disabled={readonly} className="enc-detail-textarea" /></label>
              <label>Procedures performed<textarea value={procedures} onChange={(e) => setProcedures(e.target.value)} rows={2} disabled={readonly} className="enc-detail-textarea" /></label>
              <label>Follow-up instructions<textarea value={followUpInst} onChange={(e) => setFollowUpInst(e.target.value)} rows={2} disabled={readonly} className="enc-detail-textarea" /></label>
              <label>Internal notes<textarea value={internalNotes} onChange={(e) => setInternalNotes(e.target.value)} rows={2} disabled={readonly} className="enc-detail-textarea enc-d-italic" placeholder="Only visible to staff" /></label>
            </div>
          </div>
        )}

        {/* ── Tab D: Administered Treatment ──────────────────────── */}
        {tab === "treatment" && (
          <>
            {catalogLoadFailed && <div className="workspace-alert enc-d-alert-tight" role="alert"><strong>Could not load services or inventory.</strong> Check your permissions or refresh.</div>}
            {!catalogLoadFailed && catalogServices.length === 0 && inventoryProducts.length === 0 && !readonly && (
              <div className="enc-detail-hint-box">No services or inventory items found. <Link href="/services" className="enc-d-hint-link">Add services</Link> to select them here.</div>
            )}
            <div className="enc-section surface-card">
              <div className="surface-card-heading"><div><p className="eyebrow">ADMINISTERED</p><h2>Treatments ({treatments.length})</h2></div>
                {!readonly && <div className="enc-detail-btn-group">
                  <button className="button button-secondary" type="button" onClick={addTreatment}>Add treatment</button>
                  {catalogServices.length > 0 && <button className={`button button-secondary${pickerOpen === "treat-svc" ? " enc-d-picker-active" : ""}`} type="button" onClick={() => togglePicker("treat-svc")}>Add from Service</button>}
                  {inventoryProducts.length > 0 && <button className={`button button-secondary${pickerOpen === "treat-inv" ? " enc-d-picker-active" : ""}`} type="button" onClick={() => togglePicker("treat-inv")}>Add from Inventory</button>}
                </div>}
              </div>
              {pickerOpen === "treat-svc" && (
                <div className="enc-detail-picker-wrap">
                  <input value={pickerSearch} onChange={(e) => setPickerSearch(e.target.value)} placeholder="Search services by name…" className="enc-d-picker-search" autoFocus />
                  <div className="enc-detail-picker-list">
                    {catalogServices.filter((s) => !pickerSearch || s.name.toLowerCase().includes(pickerSearch.toLowerCase())).map((svc) => (
                      <button key={svc.id} type="button" onClick={() => addTreatmentFromService(svc)} className="enc-detail-picker-item">
                        <span><strong>{svc.name}</strong>{svc.category && <span className="enc-d-picker-meta">{svc.category}</span>}</span>
                        {svc.amount_minor != null && <span className="enc-detail-price-tag">{formatPrice(svc.amount_minor, svc.currency, svc.price_mode)}</span>}
                      </button>
                    ))}
                    {catalogServices.filter((s) => !pickerSearch || s.name.toLowerCase().includes(pickerSearch.toLowerCase())).length === 0 && <div className="enc-detail-picker-empty">No services match &ldquo;{pickerSearch}&rdquo;</div>}
                  </div>
                </div>
              )}
              {pickerOpen === "treat-inv" && (
                <div className="enc-detail-picker-wrap">
                  <input value={pickerSearch} onChange={(e) => setPickerSearch(e.target.value)} placeholder="Search inventory items by name…" className="enc-d-picker-search" autoFocus />
                  <div className="enc-detail-picker-list">
                    {inventoryProducts.filter((p) => !pickerSearch || p.name.toLowerCase().includes(pickerSearch.toLowerCase())).map((prod) => (
                      <button key={prod.id} type="button" onClick={() => addTreatmentFromInventory(prod)} className="enc-detail-picker-item">
                        <span><strong>{prod.name}</strong></span>
                        <span className="enc-d-picker-sub">{prod.product_type} · {prod.unit}</span>
                      </button>
                    ))}
                    {inventoryProducts.filter((p) => !pickerSearch || p.name.toLowerCase().includes(pickerSearch.toLowerCase())).length === 0 && <div className="enc-detail-picker-empty">No items match &ldquo;{pickerSearch}&rdquo;</div>}
                  </div>
                </div>
              )}
              {treatments.length === 0 && <div className="dashboard-empty"><strong>No administered treatments</strong></div>}
              {treatments.map((t, idx) => (
                <div key={idx} className="enc-detail-item-row">
                  <label className="enc-detail-field-label-wide">Name <span className="enc-d-required">*</span>
                    <div className="enc-detail-name-flex">
                      <input value={t.name} onChange={(e) => updateTreatment(idx, "name", e.target.value)} disabled={readonly} placeholder="Treatment name (required)" className="enc-d-name-input" />
                      {t.service_id && <span className="enc-detail-badge-svc">Service</span>}
                      {t.inventory_product_id && <span className="enc-detail-badge-inv">Inventory</span>}
                      {t.unit_price_minor != null && <span className="enc-detail-price-sm">{formatPrice(t.unit_price_minor, t.currency)}</span>}
                    </div>
                  </label>
                  <label className="enc-detail-field-label">Dosage<input value={t.dosage ?? ""} onChange={(e) => updateTreatment(idx, "dosage", e.target.value)} disabled={readonly} placeholder="e.g. 500mg" /></label>
                  <label className="enc-detail-field-label">Route<input value={t.route ?? ""} onChange={(e) => updateTreatment(idx, "route", e.target.value)} disabled={readonly} placeholder="oral/IV" /></label>
                  <label className="enc-detail-field-label">Qty<input type="number" min={1} value={t.quantity ?? 1} onChange={(e) => updateTreatment(idx, "quantity", e.target.value)} disabled={readonly} className="enc-d-qty-input" /></label>
                  <label className="enc-detail-field-label">Given at<input type="datetime-local" value={t.administered_at ?? ""} onChange={(e) => updateTreatment(idx, "administered_at", e.target.value)} disabled={readonly} /></label>
                  <label className="enc-detail-field-label">Given by<input value={t.administered_by ?? ""} onChange={(e) => updateTreatment(idx, "administered_by", e.target.value)} disabled={readonly} /></label>
                  <label className="enc-detail-field-label">Response<input value={t.response ?? ""} onChange={(e) => updateTreatment(idx, "response", e.target.value)} disabled={readonly} /></label>
                  {!readonly && <button className="ghost-button enc-detail-remove-btn" type="button" onClick={() => removeTreatment(idx)}>Remove</button>}
                </div>
              ))}
            </div>
            <div className="enc-section surface-card enc-d-section-gap">
              <div className="surface-card-heading"><div><p className="eyebrow">PROCEDURES</p><h2>Administered Procedures ({adminProcedures.length})</h2></div>
                {!readonly && <div className="enc-detail-btn-group">
                  <button className="button button-secondary" type="button" onClick={addProcedure}>Add procedure</button>
                  {catalogServices.length > 0 && <button className={`button button-secondary${pickerOpen === "proc-svc" ? " enc-d-picker-active" : ""}`} type="button" onClick={() => togglePicker("proc-svc")}>Add from Service</button>}
                </div>}
              </div>
              {pickerOpen === "proc-svc" && (
                <div className="enc-detail-picker-wrap">
                  <input value={pickerSearch} onChange={(e) => setPickerSearch(e.target.value)} placeholder="Search services by name…" className="enc-d-picker-search" autoFocus />
                  <div className="enc-detail-picker-list">
                    {catalogServices.filter((s) => !pickerSearch || s.name.toLowerCase().includes(pickerSearch.toLowerCase())).map((svc) => (
                      <button key={svc.id} type="button" onClick={() => addProcedureFromService(svc)} className="enc-detail-picker-item">
                        <span><strong>{svc.name}</strong>{svc.category && <span className="enc-d-picker-meta">{svc.category}</span>}</span>
                        {svc.amount_minor != null && <span className="enc-detail-price-tag">{formatPrice(svc.amount_minor, svc.currency, svc.price_mode)}</span>}
                      </button>
                    ))}
                    {catalogServices.filter((s) => !pickerSearch || s.name.toLowerCase().includes(pickerSearch.toLowerCase())).length === 0 && <div className="enc-detail-picker-empty">No services match &ldquo;{pickerSearch}&rdquo;</div>}
                  </div>
                </div>
              )}
              {adminProcedures.length === 0 && <div className="dashboard-empty"><strong>No administered procedures</strong></div>}
              {adminProcedures.map((p, idx) => (
                <div key={idx} className="enc-detail-item-row">
                  <label className="enc-detail-field-label-wide">Name <span className="enc-d-required">*</span>
                    <div className="enc-detail-name-flex">
                      <input value={p.name} onChange={(e) => updateProcedure(idx, "name", e.target.value)} disabled={readonly} placeholder="Procedure name (required)" className="enc-d-name-input" />
                      {p.service_id && <span className="enc-detail-badge-svc">Service</span>}
                      {p.unit_price_minor != null && <span className="enc-detail-price-sm">{formatPrice(p.unit_price_minor, p.currency)}</span>}
                    </div>
                  </label>
                  <label className="enc-detail-field-label">Performed at<input type="datetime-local" value={p.performed_at ?? ""} onChange={(e) => updateProcedure(idx, "performed_at", e.target.value)} disabled={readonly} /></label>
                  <label className="enc-detail-field-label">Performer<input value={p.performer ?? ""} onChange={(e) => updateProcedure(idx, "performer", e.target.value)} disabled={readonly} /></label>
                  <label className="enc-detail-field-label-wide">Findings<input value={p.findings ?? ""} onChange={(e) => updateProcedure(idx, "findings", e.target.value)} disabled={readonly} /></label>
                  {!readonly && <button className="ghost-button enc-detail-remove-btn" type="button" onClick={() => removeProcedure(idx)}>Remove</button>}
                </div>
              ))}
            </div>
            <div className="enc-section surface-card enc-d-section-gap">
              <div className="surface-card-heading"><div><p className="eyebrow">RESPONSE</p><h2>Treatment Response</h2></div></div>
              <div className="form-grid enc-detail-grid-1col">
                <label>Treatment response<textarea value={treatmentResponse} onChange={(e) => setTreatmentResponse(e.target.value)} rows={2} disabled={readonly} className="enc-detail-textarea" placeholder="How the patient responded to treatment" /></label>
                <label>Adverse reactions<textarea value={adverseReactions} onChange={(e) => setAdverseReactions(e.target.value)} rows={2} disabled={readonly} className="enc-detail-textarea" placeholder="Any adverse reactions observed" /></label>
              </div>
            </div>
            {/* Charges summary */}
            {(() => {
              const tTotal = treatments.reduce((s, t) => s + (t.unit_price_minor ?? 0) * (t.quantity ?? 1), 0);
              const pTotal = adminProcedures.reduce((s, p) => s + (p.unit_price_minor ?? 0), 0);
              if (tTotal + pTotal <= 0) return null;
              const cur = treatments.find((t) => t.currency)?.currency ?? adminProcedures.find((p) => p.currency)?.currency ?? "PKR";
              return (
                <div className="enc-section surface-card enc-d-section-gap enc-d-summary-bg">
                  <div className="surface-card-heading"><div><p className="eyebrow">BILLING</p><h2>Charges Summary</h2></div></div>
                  <div className="enc-detail-charges-grid">
                    <div><span className="enc-d-link-muted">Treatments ({treatments.filter((t) => t.unit_price_minor).length})</span><br /><strong>{formatPrice(tTotal, cur)}</strong></div>
                    <div><span className="enc-d-link-muted">Procedures ({adminProcedures.filter((p) => p.unit_price_minor).length})</span><br /><strong>{formatPrice(pTotal, cur)}</strong></div>
                    <div><span className="enc-d-link-muted">Grand Total</span><br /><strong className="enc-d-grand-total">{formatPrice(tTotal + pTotal, cur)}</strong></div>
                  </div>
                  {invoiceData ? (
                    <div className="enc-detail-invoice-bar">
                      <span>Invoice <strong>{invoiceData.invoice_number}</strong> — <span style={{ color: invoiceData.status === "paid" ? "var(--leaf)" : "var(--accent)" }}>{invoiceData.status.toUpperCase()}</span></span>
                      <Link href={`/billing?invoice=${invoiceData.id}`} className="enc-d-inv-link-accent">View Invoice</Link>
                    </div>
                  ) : readonly && (
                    <div className="enc-d-gen-btn-gap">
                      <button className="button button-primary enc-d-xs-btn" type="button" disabled={busy} onClick={() => setShowInvoicePreview(true)}>Generate Invoice from Encounter</button>
                    </div>
                  )}
                </div>
              );
            })()}
          </>
        )}

        {/* ── Tab E: Medications ─────────────────────────────────── */}
        {tab === "medications" && (
          <div className="enc-section surface-card">
            <div className="surface-card-heading"><div><p className="eyebrow">PRESCRIPTION</p><h2>Medications ({meds.length})</h2></div>
              {!readonly && <div className="enc-detail-btn-group">
                <button className="button button-secondary" type="button" onClick={addMed}>Add medication</button>
                {inventoryProducts.filter((p) => p.product_type === "medicine").length > 0 && <button className={`button button-secondary${pickerOpen === "med-inv" ? " enc-d-picker-active" : ""}`} type="button" onClick={() => togglePicker("med-inv")}>Add from Inventory</button>}
              </div>}
            </div>
            {pickerOpen === "med-inv" && (
              <div className="enc-detail-picker-wrap">
                <input value={pickerSearch} onChange={(e) => setPickerSearch(e.target.value)} placeholder="Search medicines by name…" className="enc-d-picker-search" autoFocus />
                <div className="enc-detail-picker-list">
                  {inventoryProducts.filter((p) => p.product_type === "medicine" && (!pickerSearch || p.name.toLowerCase().includes(pickerSearch.toLowerCase()))).map((prod) => (
                    <button key={prod.id} type="button" onClick={() => addMedFromInventory(prod)} className="enc-detail-picker-item">
                      <span><strong>{prod.name}</strong></span>
                      <span className="enc-d-picker-sub">{prod.unit}</span>
                    </button>
                  ))}
                  {inventoryProducts.filter((p) => p.product_type === "medicine" && (!pickerSearch || p.name.toLowerCase().includes(pickerSearch.toLowerCase()))).length === 0 && <div className="enc-detail-picker-empty">No medicines match &ldquo;{pickerSearch}&rdquo;</div>}
                </div>
              </div>
            )}
            {meds.length === 0 && <div className="dashboard-empty"><strong>No medications</strong></div>}
            {meds.map((med, idx) => (
              <div key={idx} className="enc-detail-item-row">
                <label className="enc-detail-field-label-wide">Name <span className="enc-d-required">*</span>
                  <div className="enc-detail-name-flex">
                    <input value={med.name} onChange={(e) => updateMed(idx, "name", e.target.value)} disabled={readonly} placeholder="Medication name (required)" className="enc-d-name-input" />
                    {med.inventory_product_id && <span className="enc-detail-badge-inv">Inventory</span>}
                  </div>
                </label>
                <label className="enc-detail-field-label">Dosage<input value={med.dosage ?? ""} onChange={(e) => updateMed(idx, "dosage", e.target.value)} disabled={readonly} placeholder="e.g. 500mg" /></label>
                <label className="enc-detail-field-label">Route<input value={med.route ?? ""} onChange={(e) => updateMed(idx, "route", e.target.value)} disabled={readonly} placeholder="oral/IV" /></label>
                <label className="enc-detail-field-label">Frequency<input value={med.frequency ?? ""} onChange={(e) => updateMed(idx, "frequency", e.target.value)} disabled={readonly} placeholder="e.g. TDS" /></label>
                <label className="enc-detail-field-label">Duration<input value={med.duration ?? ""} onChange={(e) => updateMed(idx, "duration", e.target.value)} disabled={readonly} placeholder="e.g. 5 days" /></label>
                {!readonly && <button className="ghost-button enc-detail-remove-btn" type="button" onClick={() => removeMed(idx)}>Remove</button>}
              </div>
            ))}
          </div>
        )}

        {/* ── Tab F: Vitals ──────────────────────────────────────── */}
        {tab === "vitals" && (
          <div className="enc-section surface-card">
            <div className="surface-card-heading"><div><p className="eyebrow">OBSERVATIONS</p><h2>Vitals</h2></div></div>
            <div className="enc-detail-vitals-2col">
              <div>
                <p className="eyebrow enc-d-eyebrow-tight">ARRIVAL VITALS</p>
                <VitalsForm vitals={arrivalVitals} onChange={setArrivalVitals} readonly={readonly} />
                <BMIDisplay vitals={arrivalVitals} label="Arrival" />
              </div>
              <div>
                <p className="eyebrow enc-d-eyebrow-tight">DISCHARGE VITALS</p>
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
            <div className="form-grid enc-detail-grid-2col">
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
              <div className="form-grid enc-detail-grid-1col-mt">
                <label>Destination<input value={dischDestination} onChange={(e) => setDischDestination(e.target.value)} disabled={readonly} placeholder="Facility / department being referred to" /></label>
              </div>
            )}
            <div className="form-grid enc-detail-grid-1col-mt">
              <label>Discharge reason<textarea value={dischReason} onChange={(e) => setDischReason(e.target.value)} rows={2} disabled={readonly} className="enc-detail-textarea" /></label>
              <label>Discharge notes<textarea value={dischargeNotes} onChange={(e) => setDischargeNotes(e.target.value)} rows={3} disabled={readonly} className="enc-detail-textarea" /></label>
              <label>Discharge instructions<textarea value={dischInstructions} onChange={(e) => setDischInstructions(e.target.value)} rows={3} disabled={readonly} className="enc-detail-textarea" placeholder="Instructions for the patient" /></label>
              <label>Warning signs<textarea value={warningSigns} onChange={(e) => setWarningSigns(e.target.value)} rows={2} disabled={readonly} className="enc-detail-textarea" placeholder="Signs that require immediate medical attention" /></label>
              <label>Medicine guidance<textarea value={medicineGuidance} onChange={(e) => setMedicineGuidance(e.target.value)} rows={2} disabled={readonly} className="enc-detail-textarea" placeholder="Instructions for medications" /></label>
            </div>
            <div className="form-grid enc-detail-grid-3col-mt">
              <label>Follow-up clinician<input value={followUpClinician} onChange={(e) => setFollowUpClinician(e.target.value)} disabled={readonly} /></label>
              <label>Follow-up department<input value={followUpDept} onChange={(e) => setFollowUpDept(e.target.value)} disabled={readonly} /></label>
              <label>Follow-up date<input type="date" value={followUpDate} onChange={(e) => setFollowUpDate(e.target.value)} disabled={readonly} /></label>
            </div>
            {dischOutcome === "referral" && (
              <div className="form-grid enc-detail-grid-1col-mt">
                <label>Referral instructions<textarea value={referralInstructions} onChange={(e) => setReferralInstructions(e.target.value)} rows={2} disabled={readonly} className="enc-detail-textarea" /></label>
              </div>
            )}
            <div className="enc-d-section-gap">
              <p className="eyebrow enc-d-eyebrow-tight">DISCHARGE VITALS</p>
              <VitalsForm vitals={dischargeVitals} onChange={setDischargeVitals} readonly={readonly} />
            </div>
            {enc.status === "ready_for_discharge" && (
              <div className="enc-detail-discharge-divider">
                <button className="button button-primary enc-d-discharge-btn" type="button" disabled={busy} onClick={() => void completeDischarge()}>{busy ? "Discharging..." : "Complete Discharge"}</button>
              </div>
            )}
          </div>
        )}

        {/* ── Tab H: Summary / Print ──────────────────────────────── */}
        {tab === "summary" && (
          <>
            {/* Print header (hidden on screen, visible when printing) */}
            <div className="enc-section surface-card enc-print-header">
              <h2 className="enc-d-print-title">Discharge Summary</h2>
              <p>Patient: <strong>{enc.patient_name}</strong> {enc.mrn && `(MRN: ${enc.mrn})`} | Doctor: <strong>Dr. {enc.doctor_name}</strong>{enc.doctor_specialty && ` (${enc.doctor_specialty})`}</p>
              {enc.branch_name && <p>Branch: {enc.branch_name}</p>}
            </div>

            <div className="enc-section surface-card">
              <div className="surface-card-heading"><div><p className="eyebrow">DISCHARGE SUMMARY</p><h2>Encounter Summary</h2></div>
                <button className="button button-secondary" type="button" onClick={() => window.print()}>Print</button>
              </div>

              {/* Token / Reference */}
              <div className="enc-detail-ref-bar">
                <div><span className="eyebrow">TOKEN NUMBER</span><p className="enc-d-print-token">{enc.token_number != null ? enc.token_number : enc.id.slice(0, 8).toUpperCase()}</p></div>
                <div className="enc-d-print-right"><span className="eyebrow">STATUS</span><p className="enc-d-print-status" style={{ color: statusColor[enc.status] }}>{statusLabel[enc.status] ?? enc.status}</p></div>
              </div>

              {/* Arrival Vitals */}
              <div className="enc-d-section-gap">
                <p className="eyebrow enc-d-eyebrow-tight-sm">ARRIVAL VITALS</p>
                <div className="enc-detail-vitals-grid">
                  {enc.arrival_vitals?.weight_kg != null && <div><span className="enc-d-print-vitals-label">Weight</span><br /><strong>{enc.arrival_vitals.weight_kg} kg</strong></div>}
                  {enc.arrival_vitals?.height_cm != null && <div><span className="enc-d-print-vitals-label">Height</span><br /><strong>{enc.arrival_vitals.height_cm} cm</strong></div>}
                  {enc.arrival_vitals?.weight_kg != null && enc.arrival_vitals?.height_cm != null && <div><span className="enc-d-print-vitals-label">BMI</span><br /><strong>{(enc.arrival_vitals.weight_kg / ((enc.arrival_vitals.height_cm / 100) ** 2)).toFixed(1)}</strong></div>}
                  {enc.arrival_vitals?.pulse != null && <div><span className="enc-d-print-vitals-label">Pulse (BPM)</span><br /><strong>{enc.arrival_vitals.pulse}</strong></div>}
                  {enc.arrival_vitals?.blood_pressure && <div><span className="enc-d-print-vitals-label">B.P (mmHg)</span><br /><strong>{enc.arrival_vitals.blood_pressure}</strong></div>}
                  {enc.arrival_vitals?.oxygen_saturation != null && <div><span className="enc-d-print-vitals-label">SpO2%</span><br /><strong>{enc.arrival_vitals.oxygen_saturation}%</strong></div>}
                  {enc.arrival_vitals?.temperature != null && <div><span className="enc-d-print-vitals-label">Temp. (°C)</span><br /><strong>{enc.arrival_vitals.temperature}°C</strong></div>}
                  {(enc.gcs_eye != null || enc.gcs_verbal != null || enc.gcs_motor != null) && <div><span className="enc-d-print-vitals-label">GCS Score</span><br /><strong>E{enc.gcs_eye ?? "-"} V{enc.gcs_verbal ?? "-"} M{enc.gcs_motor ?? "-"} = {(enc.gcs_eye ?? 0) + (enc.gcs_verbal ?? 0) + (enc.gcs_motor ?? 0)}</strong></div>}
                </div>
              </div>

              {/* Condition on Arrival & Duration */}
              <SummarySection label="Condition on Arrival" value={enc.condition_on_arrival} />
              <SummarySection label="Duration of Symptoms" value={enc.symptom_duration} />
              {enc.arrival_mode && <SummarySection label="Arrival Mode" value={typeLabel(enc.arrival_mode)} />}
              {enc.arrival_datetime && <SummarySection label="Arrival Time" value={fmtDateTime(enc.arrival_datetime)} />}

              {/* Clinical Findings */}
              <div className="enc-d-print-section">
                <p className="eyebrow enc-d-eyebrow-tight-sm">CLINICAL FINDINGS</p>
                <SummarySection label="Chief Complaint" value={enc.chief_complaint} />
                <SummarySection label="HPI" value={enc.history_present_illness} />
                <SummarySection label="Diagnosis" value={enc.diagnosis} />
                <SummarySection label="Examination Findings" value={enc.examination_findings} />
                <SummarySection label="Clinical Assessment" value={enc.clinical_assessment} />
                {enc.pain_score != null && <SummarySection label="Pain Score" value={`${enc.pain_score}/10`} />}
                <SummarySection label="Investigations" value={enc.investigations} />
                <SummarySection label="Investigation Results" value={enc.investigation_results} />
              </div>

              {/* Treatment Given */}
              <div className="enc-d-print-section">
                <p className="eyebrow enc-d-eyebrow-tight-sm">TREATMENT GIVEN BY CLINIC</p>
                {(enc.medications?.length ?? 0) > 0 && <SummarySection label="Medicines" value={enc.medications!.map((m) => `${m.name}${m.dosage ? ` ${m.dosage}` : ""}${m.route ? ` (${m.route})` : ""}${m.frequency ? ` ${m.frequency}` : ""}${m.duration ? ` x ${m.duration}` : ""}`).join("; ")} />}
                {(enc.administered_treatments?.length ?? 0) > 0 && <SummarySection label="Treatments" value={enc.administered_treatments!.map((t) => `${t.name}${t.dosage ? ` ${t.dosage}` : ""}${t.route ? ` (${t.route})` : ""}${t.administered_by ? ` — by ${t.administered_by}` : ""}`).join("; ")} />}
                {(enc.administered_procedures?.length ?? 0) > 0 && <SummarySection label="Procedures" value={enc.administered_procedures!.map((p) => `${p.name}${p.performer ? ` by ${p.performer}` : ""}${p.findings ? ` — ${p.findings}` : ""}`).join("; ")} />}
                <SummarySection label="Treatment Plan" value={enc.treatment_plan} />
                <SummarySection label="Treatment Response" value={enc.treatment_response} />
                {enc.adverse_reactions && <SummarySection label="Adverse Reactions" value={enc.adverse_reactions} />}
              </div>

              {/* Condition at Discharge */}
              <div className="enc-d-print-section">
                <p className="eyebrow enc-d-eyebrow-tight-sm">DISCHARGE</p>
                <SummarySection label="Condition at Discharge" value={enc.discharge_condition} />
                <SummarySection label="Discharge Outcome" value={enc.discharge_outcome ? typeLabel(enc.discharge_outcome) : null} />
                {enc.discharge_datetime && <SummarySection label="Discharge Time" value={fmtDateTime(enc.discharge_datetime)} />}
              </div>

              {/* Discharge Vitals */}
              {enc.discharge_vitals && Object.values(enc.discharge_vitals).some((v) => v != null && v !== "") && (
                <div className="enc-d-print-section">
                  <p className="eyebrow enc-d-eyebrow-tight-sm">DISCHARGE VITAL SIGNS</p>
                  <div className="enc-detail-vitals-grid">
                    {enc.discharge_vitals.pulse != null && <div><span className="enc-d-print-vitals-label">Pulse (BPM)</span><br /><strong>{enc.discharge_vitals.pulse}</strong></div>}
                    {enc.discharge_vitals.blood_pressure && <div><span className="enc-d-print-vitals-label">B.P (mmHg)</span><br /><strong>{enc.discharge_vitals.blood_pressure}</strong></div>}
                    {enc.discharge_vitals.oxygen_saturation != null && <div><span className="enc-d-print-vitals-label">SpO2%</span><br /><strong>{enc.discharge_vitals.oxygen_saturation}%</strong></div>}
                    {enc.discharge_vitals.temperature != null && <div><span className="enc-d-print-vitals-label">Temp. (°C)</span><br /><strong>{enc.discharge_vitals.temperature}°C</strong></div>}
                  </div>
                </div>
              )}

              {/* Discharge Instructions */}
              <SummarySection label="Discharge Instructions" value={enc.discharge_instructions} />
              <SummarySection label="Warning Signs" value={enc.warning_signs} />

              {/* Discharge Medication Rx */}
              <SummarySection label="Discharge Medication Rx" value={enc.medicine_guidance} />
              <SummarySection label="Discharge Notes" value={enc.discharge_notes} />

              {/* Follow-up */}
              <SummarySection label="Follow-up" value={[enc.follow_up_date && `Date: ${fmtDate(enc.follow_up_date)}`, enc.follow_up_instructions, enc.follow_up_clinician && `Clinician: ${enc.follow_up_clinician}`, enc.follow_up_department && `Dept: ${enc.follow_up_department}`].filter(Boolean).join(" | ") || null} />

              {/* Examined By + Printed By */}
              <div className="enc-detail-sign-footer">
                <div>
                  <span className="eyebrow">EXAMINED BY</span>
                  <p className="enc-d-print-doctor">Dr. {enc.doctor_name}{enc.doctor_specialty && ` (${enc.doctor_specialty})`}</p>
                  <p className="enc-d-print-date">{fmtDateTime(enc.created_at)}</p>
                </div>
                <div>
                  <span className="eyebrow">{enc.discharged_by ? "DISCHARGED BY" : "PRINTED BY"}</span>
                  <p className="enc-d-print-doctor">{enc.discharged_by ?? `Dr. ${enc.doctor_name}`}</p>
                  {enc.discharge_datetime && <p className="enc-d-print-date">{fmtDateTime(enc.discharge_datetime)}</p>}
                </div>
              </div>

              {enc.internal_notes && <div className="enc-detail-internal-note"><span className="eyebrow">INTERNAL NOTES (NOT PRINTED)</span><p>{enc.internal_notes}</p></div>}
            </div>

            {/* Amendment history */}
            {(enc.amendment_history?.length ?? 0) > 0 && (
              <div className="enc-section surface-card enc-d-section-gap">
                <div className="surface-card-heading"><div><p className="eyebrow">AUDIT</p><h2>Amendment History</h2></div></div>
                {enc.amendment_history!.map((a, idx) => (
                  <div key={idx} className="enc-d-amend-row">
                    <strong>{AMENDABLE_FIELDS.find((f) => f.value === a.field)?.label ?? a.field}</strong> amended on {fmtDateTime(a.amended_at)}
                    <p className="enc-d-amend-reason">Reason: {a.reason}</p>
                    <p className="enc-d-amend-value">New value: {a.new_value.length > 200 ? a.new_value.slice(0, 200) + "..." : a.new_value}</p>
                  </div>
                ))}
              </div>
            )}

            {/* Amend form */}
            {(enc.status === "discharged" || enc.status === "finalized") && (
              <div className="enc-section surface-card enc-d-section-gap">
                <div className="surface-card-heading"><div><p className="eyebrow">CORRECTION</p><h2>Amend Record</h2></div></div>
                <div className="form-grid enc-detail-grid-2col">
                  <label>Field to amend
                    <select value={amendField} onChange={(e) => { setAmendField(e.target.value); setAmendNewValue(""); }}>
                      <option value="">Select field...</option>
                      {AMENDABLE_FIELDS.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
                    </select>
                  </label>
                  {amendField && (
                    <div><span className="eyebrow">CURRENT VALUE</span><p className="enc-d-amend-current">{((enc as Record<string, unknown>)[amendField] as string) || "(empty)"}</p></div>
                  )}
                </div>
                {amendField && (
                  <div className="form-grid enc-detail-grid-1col-mt">
                    <label>New value<textarea value={amendNewValue} onChange={(e) => setAmendNewValue(e.target.value)} rows={3} className="enc-detail-textarea" /></label>
                    <label>Reason for amendment<textarea value={amendReason} onChange={(e) => setAmendReason(e.target.value)} rows={2} className="enc-detail-textarea" placeholder="Required: explain why this amendment is needed" /></label>
                    <div><button className="button button-secondary" type="button" disabled={busy || !amendNewValue || !amendReason} onClick={() => void submitAmendment()}>{busy ? "Submitting..." : "Submit Amendment"}</button></div>
                  </div>
                )}
              </div>
            )}
          </>
        )}

        {/* Save button (not on discharge or summary tabs) */}
        {!readonly && tab !== "summary" && tab !== "discharge" && (
          <div className="form-actions enc-d-form-gap">
            <button className="button button-primary" type="submit" disabled={busy}>{busy ? "Saving..." : "Save encounter"}</button>
          </div>
        )}
        {/* Discharge tab: also allow saving without completing discharge */}
        {!readonly && tab === "discharge" && enc.status !== "ready_for_discharge" && (
          <div className="form-actions enc-d-form-gap">
            <button className="button button-primary" type="submit" disabled={busy}>{busy ? "Saving..." : "Save encounter"}</button>
          </div>
        )}
      </form>
    </main>
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
    <div className="enc-detail-alt-panel enc-d-section-gap">
      <p className="eyebrow enc-d-eyebrow-tight-xs">GLASGOW COMA SCALE (GCS)</p>
      <div className="enc-detail-gcs-grid">
        <label className="enc-detail-gcs-label">Eye Response (E)
          <select value={eye ?? ""} onChange={(e) => onChange("eye", e.target.value === "" ? null : parseInt(e.target.value, 10))} disabled={readonly}>
            <option value="">-</option>
            {GCS_EYE.map((o) => <option key={o.v} value={o.v}>{o.l}</option>)}
          </select>
        </label>
        <label className="enc-detail-gcs-label">Verbal Response (V)
          <select value={verbal ?? ""} onChange={(e) => onChange("verbal", e.target.value === "" ? null : parseInt(e.target.value, 10))} disabled={readonly}>
            <option value="">-</option>
            {GCS_VERBAL.map((o) => <option key={o.v} value={o.v}>{o.l}</option>)}
          </select>
        </label>
        <label className="enc-detail-gcs-label">Motor Response (M)
          <select value={motor ?? ""} onChange={(e) => onChange("motor", e.target.value === "" ? null : parseInt(e.target.value, 10))} disabled={readonly}>
            <option value="">-</option>
            {GCS_MOTOR.map((o) => <option key={o.v} value={o.v}>{o.l}</option>)}
          </select>
        </label>
        <div className="enc-d-gcs-total">
          <p className="enc-d-gcs-label">TOTAL</p>
          <p className="enc-d-gcs-score">{hasAll ? total : "-"}</p>
          {classification && <p className="enc-d-bmi-cat" style={{ fontWeight: 600, color: classColor }}>{classification}</p>}
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
    <div className="enc-detail-bmi">
      <span className="enc-d-bmi-label">{label} BMI:</span>
      <span className="enc-d-bmi-value" style={{ color }}>{bmiStr}</span>
      <span className="enc-d-bmi-cat" style={{ color }}>({category})</span>
    </div>
  );
}

/* ── Summary Section ───────────────────────────────────────────────── */
function SummarySection({ label, value }: { label: string; value: string | null | undefined }) {
  if (!value) return null;
  return (
    <div className="enc-detail-summary-row">
      <span className="eyebrow">{label.toUpperCase()}</span>
      <p className="enc-d-finding-text">{value}</p>
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
