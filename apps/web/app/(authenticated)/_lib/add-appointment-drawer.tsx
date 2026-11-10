"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import Drawer, { useDirty } from "./drawer";
import { useToast } from "./toast";
import { api, writeHeaders } from "./client";
import { useClinicName } from "./clinic-context";

type Option = { id: string; name?: string; public_name?: string };
type Patient = { id: string; full_name: string; patient_number?: string };
type PatientDetail = { id: string; full_name: string; normalized_phone: string | null; version: number };

function digitCount(value: string): number {
  return (value.match(/\d/g) || []).length;
}
type Props = {
  open: boolean;
  onClose: () => void;
  clinicSlug?: string;
  onCreated?: () => void;
};

function todayStr(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}T${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function dobFromAge(age: number): string {
  const d = new Date();
  d.setFullYear(d.getFullYear() - age);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export default function AddAppointmentDrawer({ open, onClose, onCreated }: Props) {
  const toast = useToast();
  const clinicName = useClinicName();
  const [form, setForm, dirty, resetDirty] = useDirty({
    doctor_id: "", service_id: "", branch_id: "",
    appointment_type: "day",
    starts_at: todayStr(),
    patient_mode: "existing" as "existing" | "new",
    patient_id: "",
    full_name: "", email: "", phone: "",
    dob_mode: "age" as "age" | "dob",
    date_of_birth: "", age: "",
    payment_method: "cash",
  });
  const [branches, setBranches] = useState<Option[]>([]);
  const [doctors, setDoctors] = useState<Option[]>([]);
  const [branchServices, setBranchServices] = useState<Option[]>([]);
  const [branchDoctors, setBranchDoctors] = useState<Option[]>([]);
  const [doctorServiceIds, setDoctorServiceIds] = useState<Set<string>>(new Set());
  const [patients, setPatients] = useState<Patient[]>([]);
  const [patientSearch, setPatientSearch] = useState("");
  const [busy, setBusy] = useState(false);
  const [step, setStep] = useState(1);
  const [branchLoadError, setBranchLoadError] = useState(false);
  const [serviceLoadError, setServiceLoadError] = useState(false);
  const [bookingResult, setBookingResult] = useState<{ reference: string; token_number: number; starts_at: string } | null>(null);
  const [slotDate, setSlotDate] = useState(() => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; });
  const [availableSlots, setAvailableSlots] = useState<string[]>([]);
  const [loadingSlots, setLoadingSlots] = useState(false);
  const [selectedPatientDetail, setSelectedPatientDetail] = useState<PatientDetail | null>(null);
  const [existingPhoneDraft, setExistingPhoneDraft] = useState("");
  const [savingExistingPhone, setSavingExistingPhone] = useState(false);

  useEffect(() => {
    if (!open) return;
    void Promise.all([
      api<Option[]>("/api/v1/branches?limit=100"),
      api<Option[]>("/api/v1/doctors?limit=100"),
      api<Patient[]>("/api/v1/patients?limit=100"),
    ]).then(([b, d, p]) => {
      setBranches(b ?? []);
      setDoctors(d ?? []);
      setPatients(p ?? []);
    }).catch(() => undefined);
  }, [open]);

  useEffect(() => {
    if (!form.branch_id) { setBranchServices([]); setBranchDoctors([]); setBranchLoadError(false); setServiceLoadError(false); return; }
    setBranchLoadError(false);
    setServiceLoadError(false);
    void api<Option[]>(`/api/v1/branches/${form.branch_id}/services?limit=100`)
      .then((s) => setBranchServices(s ?? []))
      .catch(() => { setServiceLoadError(true); setBranchServices([]); });
    void api<Option[]>(`/api/v1/branches/${form.branch_id}/doctors?limit=100`)
      .then((d) => setBranchDoctors(d ?? []))
      .catch(() => { setBranchLoadError(true); setBranchDoctors([]); });
  }, [form.branch_id]);

  useEffect(() => {
    if (!form.branch_id || !form.doctor_id || !form.service_id || !slotDate) { setAvailableSlots([]); return; }
    setLoadingSlots(true);
    const params = new URLSearchParams({ branch_id: form.branch_id, service_id: form.service_id, doctor_id: form.doctor_id, from_date: slotDate, to_date: slotDate });
    void api<string[]>(`/api/v1/appointments/availability?${params.toString()}`).then((slots) => {
      setAvailableSlots(slots ?? []);
    }).catch(() => setAvailableSlots([])).finally(() => setLoadingSlots(false));
  }, [form.branch_id, form.doctor_id, form.service_id, slotDate]);

  useEffect(() => {
    if (!form.doctor_id) { setDoctorServiceIds(new Set()); return; }
    type DoctorDetail = { services?: { id: string }[] };
    void api<DoctorDetail>(`/api/v1/doctors/${form.doctor_id}`).then((d) => {
      setDoctorServiceIds(new Set((d?.services ?? []).map((s) => s.id)));
    }).catch(() => setDoctorServiceIds(new Set()));
  }, [form.doctor_id]);

  useEffect(() => {
    if (!form.patient_id || form.patient_mode !== "existing") { setSelectedPatientDetail(null); setExistingPhoneDraft(""); return; }
    void api<PatientDetail>(`/api/v1/patients/${form.patient_id}`).then((p) => {
      if (p) { setSelectedPatientDetail(p); setExistingPhoneDraft(p.normalized_phone ?? ""); }
    }).catch(() => { setSelectedPatientDetail(null); setExistingPhoneDraft(""); });
  }, [form.patient_id, form.patient_mode]);

  async function saveExistingPatientPhone() {
    if (!selectedPatientDetail) return;
    if (digitCount(existingPhoneDraft) < 7) { toast.error("Enter a valid phone with at least 7 digits."); return; }
    setSavingExistingPhone(true);
    try {
      const updated = await api<PatientDetail>(`/api/v1/patients/${selectedPatientDetail.id}`, {
        method: "PATCH",
        headers: writeHeaders(),
        body: JSON.stringify({ expected_version: selectedPatientDetail.version, phone: existingPhoneDraft.trim() }),
      });
      if (updated) setSelectedPatientDetail(updated);
      toast.success("Phone saved.");
    } catch (reason) {
      toast.error(reason instanceof Error ? reason.message : "Could not save phone.");
    } finally {
      setSavingExistingPhone(false);
    }
  }

  const reset = useCallback(() => {
    setForm(() => ({
      doctor_id: "", service_id: "", branch_id: "",
      appointment_type: "day", starts_at: todayStr(),
      patient_mode: "existing" as const, patient_id: "",
      full_name: "", email: "", phone: "",
      dob_mode: "age" as const, date_of_birth: "", age: "",
      payment_method: "cash",
    }));
    resetDirty();
    setStep(1);
    setPatientSearch("");
    setBranchServices([]);
    setBranchDoctors([]);
    setDoctorServiceIds(new Set());
    setBranchLoadError(false);
    setBookingResult(null);
    setAvailableSlots([]);
    setSlotDate(() => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; });
  }, [setForm, resetDirty]);

  useEffect(() => { if (!open) reset(); }, [open, reset]);

  const filteredPatients = patients.filter((p) =>
    !patientSearch || p.full_name.toLowerCase().includes(patientSearch.toLowerCase())
  );

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!form.branch_id || !form.service_id || !form.starts_at) return;
    if (form.patient_mode === "existing" && !form.patient_id) return;
    if (form.patient_mode === "new" && !form.full_name.trim()) return;
    setBusy(true);
    try {
      const body: Record<string, unknown> = {
        branch_id: form.branch_id,
        service_id: form.service_id,
        starts_at: new Date(form.starts_at).toISOString(),
      };
      if (form.doctor_id) body.doctor_id = form.doctor_id;
      if (form.patient_mode === "existing") {
        body.patient_id = form.patient_id;
      } else {
        body.full_name = form.full_name.trim();
        if (form.email.trim()) body.email = form.email.trim();
        if (form.phone.trim()) body.phone = form.phone.trim();
        if (form.dob_mode === "age" && form.age) {
          body.date_of_birth = dobFromAge(Number(form.age));
        } else if (form.dob_mode === "dob" && form.date_of_birth) {
          body.date_of_birth = form.date_of_birth;
        }
      }
      body.appointment_type = form.appointment_type;
      body.payment_method = form.payment_method;

      const result = await api<{ reference?: string; token_number?: number; starts_at?: string }>("/api/v1/appointments", {
        method: "POST",
        headers: { ...writeHeaders(), "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify(body),
      });
      toast.success(`Appointment ${result?.reference ?? ""} booked.`);
      onCreated?.();
      if (result?.token_number) {
        setBookingResult({ reference: result.reference ?? "", token_number: result.token_number, starts_at: result.starts_at ?? form.starts_at });
        setStep(6);
      } else {
        onClose();
      }
    } catch (reason) {
      toast.error(reason instanceof Error ? reason.message : "The appointment could not be booked.");
    } finally {
      setBusy(false);
    }
  }

  const canProceed = (s: number) => {
    if (s === 1) return !!form.branch_id && !!form.doctor_id;
    if (s === 2) return true;
    if (s === 3) return !!form.starts_at && !!form.service_id;
    if (s === 4) {
      if (form.patient_mode === "existing") {
        if (!form.patient_id) return false;
        return !!selectedPatientDetail?.normalized_phone && digitCount(selectedPatientDetail.normalized_phone) >= 7;
      }
      return !!form.full_name.trim() && digitCount(form.phone) >= 7;
    }
    return true;
  };

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title="Book appointment"
      subtitle="NEW BOOKING"
      dirty={dirty}
      footer={step === 6 ? undefined :
        <>
          {step > 1 && <button className="button button-secondary" type="button" onClick={() => setStep((s) => s - 1)} disabled={busy}>← Back</button>}
          {step < 5 && <button className="button button-primary" type="button" onClick={() => setStep((s) => s + 1)} disabled={!canProceed(step)}>Next <span>→</span></button>}
          {step === 5 && <button className="button button-primary" type="submit" form="add-appointment-form" disabled={busy}>{busy ? "Booking…" : "Confirm booking"} <span>→</span></button>}
        </>
      }
    >
      <form id="add-appointment-form" className="drawer-form" onSubmit={submit}>
        {/* Step indicator */}
        <div style={{ display: "flex", gap: 6, marginBottom: 20 }}>
          {[1, 2, 3, 4, 5].map((s) => (
            <div key={s} style={{ flex: 1, height: 4, borderRadius: 2, background: s <= step ? "var(--leaf, #274c42)" : "var(--line, #e5e5e3)", transition: "background .2s" }} />
          ))}
        </div>

        {/* Step 1: Select Branch then Doctor */}
        {step === 1 && <>
          <p className="eyebrow" style={{ marginBottom: 12 }}>STEP 1 — BRANCH & DOCTOR</p>
          <label style={{ display: "grid", gap: 6, marginBottom: 16 }}>
            <span style={{ fontSize: 11, color: "var(--muted)", fontWeight: 500 }}>Branch</span>
            <select required value={form.branch_id} onChange={(e) => setForm((f) => ({ ...f, branch_id: e.target.value, doctor_id: "", service_id: "" }))}>
              <option value="">Select branch</option>
              {branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
            </select>
          </label>
          {form.branch_id && <>
            <span style={{ fontSize: 11, color: "var(--muted)", fontWeight: 500, display: "block", marginBottom: 8 }}>Doctor</span>
            <div style={{ display: "grid", gap: 8 }}>
              {branchDoctors.map((d) => (
                <button
                  key={d.id}
                  type="button"
                  className={`button ${form.doctor_id === d.id ? "button-primary" : "button-secondary"}`}
                  style={{ justifyContent: "flex-start", padding: "12px 16px", width: "100%" }}
                  onClick={() => setForm((f) => ({ ...f, doctor_id: d.id }))}
                >
                  {d.public_name ?? d.name}
                </button>
              ))}
              {branchDoctors.length === 0 && <p style={{ color: branchLoadError ? "var(--coral, #a14937)" : "var(--muted)", fontSize: 13 }}>
                {branchLoadError ? "Could not load doctors for this branch. Please try again." : <>No doctors assigned to this branch. Assign doctors from the <Link href="/branches" style={{ color: "var(--leaf, #274c42)" }}>Branches</Link> page.</>}
              </p>}
            </div>
          </>}
        </>}

        {/* Step 2: Appointment Type */}
        {step === 2 && <>
          <p className="eyebrow" style={{ marginBottom: 12 }}>STEP 2 — APPOINTMENT TYPE</p>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            <button
              type="button"
              className={`button ${form.appointment_type === "day" ? "button-primary" : "button-secondary"}`}
              style={{ padding: "18px 16px", flexDirection: "column", gap: 6 }}
              onClick={() => setForm((f) => ({ ...f, appointment_type: "day" }))}
            >
              <span style={{ fontSize: 24 }}>☀</span>
              Day
            </button>
            <button
              type="button"
              className={`button ${form.appointment_type === "evening" ? "button-primary" : "button-secondary"}`}
              style={{ padding: "18px 16px", flexDirection: "column", gap: 6 }}
              onClick={() => setForm((f) => ({ ...f, appointment_type: "evening" }))}
            >
              <span style={{ fontSize: 24 }}>☽</span>
              Evening
            </button>
          </div>
        </>}

        {/* Step 3: Date, Time, Service */}
        {step === 3 && (() => {
          const availableServices = doctorServiceIds.size > 0
            ? branchServices.filter((s) => doctorServiceIds.has(s.id))
            : branchServices;
          return <>
            <p className="eyebrow" style={{ marginBottom: 12 }}>STEP 3 — DATE, SERVICE & TIME</p>
            <span style={{ fontSize: 11, color: "var(--muted)", fontWeight: 500, display: "block", marginBottom: 8 }}>Service</span>
            <div style={{ display: "grid", gap: 8 }}>
              {availableServices.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  className={`button ${form.service_id === s.id ? "button-primary" : "button-secondary"}`}
                  style={{ justifyContent: "flex-start", padding: "12px 16px", width: "100%" }}
                  onClick={() => setForm((f) => ({ ...f, service_id: s.id }))}
                >
                  {s.name}
                </button>
              ))}
              {availableServices.length === 0 && <p style={{ color: serviceLoadError ? "var(--coral, #a14937)" : "var(--muted)", fontSize: 13 }}>
                {serviceLoadError ? "Could not load services. Please try again." : doctorServiceIds.size > 0 ? "This doctor has no services at this branch. Assign services from the Branches page." : "No services assigned to this branch. Assign services from the Branches page."}
              </p>}
            </div>
            {form.service_id && <>
              <label style={{ display: "grid", gap: 6, margin: "16px 0 8px" }}>
                <span style={{ fontSize: 11, color: "var(--muted)", fontWeight: 500 }}>Date</span>
                <input type="date" value={slotDate} onChange={(e) => { setSlotDate(e.target.value); setForm((f) => ({ ...f, starts_at: "" })); }} />
              </label>
              <span style={{ fontSize: 11, color: "var(--muted)", fontWeight: 500, display: "block", marginBottom: 8 }}>Available times</span>
              {loadingSlots && <p style={{ color: "var(--muted)", fontSize: 13 }}>Loading available times…</p>}
              {!loadingSlots && availableSlots.length === 0 && <p style={{ color: "var(--muted)", fontSize: 13 }}>No pre-defined slots for this date — pick any time below.</p>}
              {!loadingSlots && availableSlots.length > 0 && <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(90px, 1fr))", gap: 6 }}>
                {availableSlots.map((slot) => {
                  const d = new Date(slot);
                  const iso = d.toISOString();
                  return <button key={slot} type="button" className={`button ${form.starts_at === iso ? "button-primary" : "button-secondary"}`} style={{ padding: "8px 4px", fontSize: 13 }} onClick={() => setForm((f) => ({ ...f, starts_at: iso }))}>{d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}</button>;
                })}
              </div>}
              <label style={{ display: "grid", gap: 6, marginTop: 10 }}>
                <span style={{ fontSize: 11, color: "var(--muted)", fontWeight: 500 }}>Custom time</span>
                <input
                  type="time"
                  value={form.starts_at ? (() => { const d = new Date(form.starts_at); return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`; })() : ""}
                  onChange={(e) => {
                    const t = e.target.value;
                    if (!t) { setForm((f) => ({ ...f, starts_at: "" })); return; }
                    const d = new Date(`${slotDate}T${t}`);
                    if (!isNaN(d.getTime())) setForm((f) => ({ ...f, starts_at: d.toISOString() }));
                  }}
                />
              </label>
            </>}
          </>;
        })()}

        {/* Step 4: Select or Create Patient */}
        {step === 4 && <>
          <p className="eyebrow" style={{ marginBottom: 12 }}>STEP 4 — PATIENT</p>
          <div style={{ display: "flex", gap: 8, marginBottom: 14 }}>
            <button type="button" className={`button ${form.patient_mode === "existing" ? "button-primary" : "button-secondary"}`} style={{ flex: 1 }} onClick={() => setForm((f) => ({ ...f, patient_mode: "existing" as const }))}>Existing patient</button>
            <button type="button" className={`button ${form.patient_mode === "new" ? "button-primary" : "button-secondary"}`} style={{ flex: 1 }} onClick={() => setForm((f) => ({ ...f, patient_mode: "new" as const }))}>New patient</button>
          </div>

          {form.patient_mode === "existing" && <>
            <input
              placeholder="Search patients…"
              value={patientSearch}
              onChange={(e) => setPatientSearch(e.target.value)}
              style={{ width: "100%", marginBottom: 10, padding: "10px 12px", border: "1px solid var(--line)", background: "white", fontSize: 13 }}
            />
            <div style={{ maxHeight: 200, overflowY: "auto", display: "grid", gap: 4 }}>
              {filteredPatients.slice(0, 20).map((p) => (
                <button
                  key={p.id}
                  type="button"
                  className={`button ${form.patient_id === p.id ? "button-primary" : "button-secondary"}`}
                  style={{ justifyContent: "flex-start", padding: "10px 14px", width: "100%", fontSize: 13 }}
                  onClick={() => setForm((f) => ({ ...f, patient_id: p.id }))}
                >
                  {p.full_name}{p.patient_number ? ` · ${p.patient_number}` : ""}
                </button>
              ))}
              {filteredPatients.length === 0 && <p style={{ color: "var(--muted)", fontSize: 12 }}>No patients found. Try a different search or add a new patient.</p>}
            </div>
            {selectedPatientDetail && !selectedPatientDetail.normalized_phone && (
              <div style={{ marginTop: 14, padding: 12, border: "1px solid var(--coral, #a14937)", borderRadius: 8, background: "rgba(161,73,55,0.05)" }}>
                <p style={{ margin: 0, marginBottom: 8, fontSize: 12, color: "var(--coral, #a14937)" }}>This patient has no phone on file. Add one to continue.</p>
                <div style={{ display: "flex", gap: 8 }}>
                  <input
                    type="tel"
                    inputMode="tel"
                    placeholder="+92 300 1234567"
                    value={existingPhoneDraft}
                    onChange={(e) => setExistingPhoneDraft(e.target.value)}
                    style={{ flex: 1, padding: "8px 10px", border: "1px solid var(--line)", background: "white" }}
                  />
                  <button type="button" className="button button-primary" disabled={savingExistingPhone} onClick={() => void saveExistingPatientPhone()}>
                    {savingExistingPhone ? "Saving…" : "Save phone"}
                  </button>
                </div>
              </div>
            )}
            {selectedPatientDetail?.normalized_phone && (
              <p style={{ marginTop: 10, fontSize: 11, color: "var(--muted)" }}>Phone on file: {selectedPatientDetail.normalized_phone}</p>
            )}
          </>}

          {form.patient_mode === "new" && <div className="form-grid">
            <label>Full name<input required maxLength={160} value={form.full_name} onChange={(e) => setForm((f) => ({ ...f, full_name: e.target.value }))} placeholder="Patient's full name" /></label>
            <label>Email<input type="email" maxLength={320} value={form.email} onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))} placeholder="patient@example.com" /></label>
            <label>Phone *<input required type="tel" inputMode="tel" maxLength={40} value={form.phone} onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))} placeholder="+92 300 1234567" style={digitCount(form.phone) < 7 ? { borderColor: "var(--coral, #a14937)", background: "rgba(161,73,55,0.05)" } : undefined} />{digitCount(form.phone) < 7 && <small style={{ color: "var(--coral, #a14937)", fontSize: 11, display: "block", marginTop: 4 }}>Phone is required (at least 7 digits).</small>}</label>
            <div style={{ display: "flex", gap: 8, marginBottom: 4 }}>
              <button type="button" className={`button ${form.dob_mode === "age" ? "button-primary" : "button-secondary"}`} style={{ flex: 1, padding: "6px 10px", fontSize: 11 }} onClick={() => setForm((f) => ({ ...f, dob_mode: "age" as const }))}>Enter age</button>
              <button type="button" className={`button ${form.dob_mode === "dob" ? "button-primary" : "button-secondary"}`} style={{ flex: 1, padding: "6px 10px", fontSize: 11 }} onClick={() => setForm((f) => ({ ...f, dob_mode: "dob" as const }))}>Date of birth</button>
            </div>
            {form.dob_mode === "age"
              ? <label>Age<input type="number" min={0} max={150} value={form.age} onChange={(e) => setForm((f) => ({ ...f, age: e.target.value }))} placeholder="Years" /></label>
              : <label>Date of birth<input type="date" value={form.date_of_birth} onChange={(e) => setForm((f) => ({ ...f, date_of_birth: e.target.value }))} /></label>
            }
          </div>}
        </>}

        {/* Step 6: Booking Success + Print Token */}
        {step === 6 && bookingResult && <>
          <div style={{ textAlign: "center", padding: "20px 0" }}>
            <div style={{ fontSize: 48, marginBottom: 12 }}>✓</div>
            <h2 style={{ margin: "0 0 8px", fontSize: 20 }}>Appointment Booked</h2>
            <p style={{ color: "var(--muted)", fontSize: 13, margin: 0 }}>Reference: {bookingResult.reference}</p>
          </div>
          <div id="token-print-area" style={{ background: "var(--paper, #f9f9f6)", padding: 20, borderRadius: 10, border: "2px dashed var(--line, #e5e5e3)", marginBottom: 16 }}>
            {clinicName && <div className="clinic-heading" style={{ textAlign: "center", fontSize: 18, fontWeight: 700, letterSpacing: 0.3, color: "var(--leaf, #274c42)", borderBottom: "1px solid var(--line, #e5e5e3)", paddingBottom: 8, marginBottom: 10 }}>{clinicName}</div>}
            <div style={{ textAlign: "center", marginBottom: 12 }}>
              <p className="eyebrow" style={{ margin: "0 0 4px" }}>TOKEN NUMBER</p>
              <div className="token" style={{ fontSize: 48, fontWeight: 700, color: "var(--leaf, #274c42)" }}>{bookingResult.token_number}</div>
            </div>
            <dl style={{ margin: 0, display: "grid", gap: 6, fontSize: 13 }}>
              <div style={{ display: "flex", justifyContent: "space-between" }}><dt style={{ color: "var(--muted)", fontSize: 11 }}>Patient</dt><dd style={{ margin: 0 }}>{form.patient_mode === "existing" ? (patients.find((p) => p.id === form.patient_id)?.full_name ?? "—") : form.full_name || "—"}</dd></div>
              <div style={{ display: "flex", justifyContent: "space-between" }}><dt style={{ color: "var(--muted)", fontSize: 11 }}>Doctor</dt><dd style={{ margin: 0 }}>{(branchDoctors.find((d) => d.id === form.doctor_id) ?? doctors.find((d) => d.id === form.doctor_id))?.public_name ?? "—"}</dd></div>
              <div style={{ display: "flex", justifyContent: "space-between" }}><dt style={{ color: "var(--muted)", fontSize: 11 }}>Service</dt><dd style={{ margin: 0 }}>{branchServices.find((s) => s.id === form.service_id)?.name ?? "—"}</dd></div>
              <div style={{ display: "flex", justifyContent: "space-between" }}><dt style={{ color: "var(--muted)", fontSize: 11 }}>Date/Time</dt><dd style={{ margin: 0 }}>{new Date(bookingResult.starts_at).toLocaleString(undefined, { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}</dd></div>
              <div style={{ display: "flex", justifyContent: "space-between" }}><dt style={{ color: "var(--muted)", fontSize: 11 }}>Reference</dt><dd style={{ margin: 0 }}>{bookingResult.reference}</dd></div>
            </dl>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button className="button button-primary" type="button" style={{ flex: 1 }} onClick={() => {
              const el = document.getElementById("token-print-area");
              if (!el) return;
              const w = window.open("", "_blank", "width=400,height=500");
              if (!w) return;
              w.document.write(`<html><head><title>Token ${bookingResult.token_number}</title><style>@page{size:80mm 70mm;margin:2mm}html,body{margin:0;padding:0;background:#fff;color:#000;-webkit-print-color-adjust:exact;print-color-adjust:exact}body{font-family:system-ui,-apple-system,sans-serif;padding:4px;width:76mm;box-sizing:border-box;word-wrap:break-word}*{box-sizing:border-box}#token-print-area{background:#fff!important;padding:4px!important;border:0!important;margin:0!important;border-radius:0!important;page-break-inside:avoid}.clinic-heading{text-align:center!important;font-size:14px!important;font-weight:700!important;letter-spacing:.3px;color:#000!important;border-bottom:1px solid #000!important;padding-bottom:4px!important;margin:0 0 6px!important;line-height:1.1;page-break-inside:avoid}dt{color:#333;font-size:10px}dd{margin:0;font-size:12px;font-weight:600}dl{display:grid;gap:3px;margin:0}dl>div{display:flex;justify-content:space-between;gap:6px;page-break-inside:avoid}.token{font-size:34px!important;font-weight:700!important;text-align:center;margin:4px 0!important;line-height:1;page-break-inside:avoid;color:#000!important}.eyebrow{font-size:9px;letter-spacing:1px;text-transform:uppercase;text-align:center;margin:0 0 2px;color:#333}@media print{button{display:none!important}html,body{background:#fff!important;color:#000!important}}@media print and (max-width:60mm){@page{size:58mm 65mm;margin:1.5mm}body{width:54mm;padding:2px}.token{font-size:26px!important;margin:3px 0!important}dd{font-size:11px}.clinic-heading{font-size:12px!important}}</style></head><body>${el.innerHTML}</body></html>`);
              w.document.close();
              w.print();
            }}>Print Token</button>
            <button className="button button-secondary" type="button" style={{ flex: 1 }} onClick={onClose}>Close</button>
          </div>
        </>}

        {/* Step 5: Payment Method + Review */}
        {step === 5 && <>
          <p className="eyebrow" style={{ marginBottom: 12 }}>STEP 5 — PAYMENT & CONFIRM</p>
          <label style={{ display: "grid", gap: 7, color: "var(--muted)", fontSize: 11, fontFamily: "'DM Mono', monospace", marginBottom: 16 }}>
            PAYMENT METHOD
            <select value={form.payment_method} onChange={(e) => setForm((f) => ({ ...f, payment_method: e.target.value }))}>
              <option value="cash">Cash</option>
              <option value="card">Card</option>
              <option value="online">Online transfer</option>
              <option value="insurance">Insurance</option>
            </select>
          </label>

          <div style={{ background: "var(--paper, #f9f9f6)", padding: 16, borderRadius: 10 }}>
            <p className="eyebrow" style={{ marginBottom: 10 }}>BOOKING SUMMARY</p>
            <dl style={{ margin: 0, display: "grid", gap: 8, fontSize: 13 }}>
              <div style={{ display: "flex", justifyContent: "space-between" }}><dt style={{ color: "var(--muted)", fontSize: 11 }}>Branch</dt><dd style={{ margin: 0 }}>{branches.find((b) => b.id === form.branch_id)?.name ?? "—"}</dd></div>
              <div style={{ display: "flex", justifyContent: "space-between" }}><dt style={{ color: "var(--muted)", fontSize: 11 }}>Doctor</dt><dd style={{ margin: 0 }}>{(branchDoctors.find((d) => d.id === form.doctor_id) ?? doctors.find((d) => d.id === form.doctor_id))?.public_name ?? "—"}</dd></div>
              <div style={{ display: "flex", justifyContent: "space-between" }}><dt style={{ color: "var(--muted)", fontSize: 11 }}>Service</dt><dd style={{ margin: 0 }}>{branchServices.find((s) => s.id === form.service_id)?.name ?? "—"}</dd></div>
              <div style={{ display: "flex", justifyContent: "space-between" }}><dt style={{ color: "var(--muted)", fontSize: 11 }}>Type</dt><dd style={{ margin: 0 }}>{form.appointment_type === "day" ? "☀ Day" : "☽ Evening"}</dd></div>
              <div style={{ display: "flex", justifyContent: "space-between" }}><dt style={{ color: "var(--muted)", fontSize: 11 }}>When</dt><dd style={{ margin: 0 }}>{form.starts_at ? new Date(form.starts_at).toLocaleString(undefined, { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "—"}</dd></div>
              <div style={{ display: "flex", justifyContent: "space-between" }}><dt style={{ color: "var(--muted)", fontSize: 11 }}>Patient</dt><dd style={{ margin: 0 }}>{form.patient_mode === "existing" ? (patients.find((p) => p.id === form.patient_id)?.full_name ?? "—") : form.full_name || "—"}</dd></div>
              <div style={{ display: "flex", justifyContent: "space-between" }}><dt style={{ color: "var(--muted)", fontSize: 11 }}>Payment</dt><dd style={{ margin: 0, textTransform: "capitalize" }}>{form.payment_method}</dd></div>
            </dl>
          </div>
        </>}
      </form>
    </Drawer>
  );
}
