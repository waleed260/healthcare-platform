"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import Drawer, { useDirty } from "./drawer";
import { useToast } from "./toast";
import { api, writeHeaders } from "./client";

type Option = { id: string; name?: string; public_name?: string };
type Patient = { id: string; full_name: string; patient_number?: string };
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

export default function AddAppointmentDrawer({ open, onClose, clinicSlug, onCreated }: Props) {
  const toast = useToast();
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
  const [services, setServices] = useState<Option[]>([]);
  const [doctors, setDoctors] = useState<Option[]>([]);
  const [patients, setPatients] = useState<Patient[]>([]);
  const [patientSearch, setPatientSearch] = useState("");
  const [busy, setBusy] = useState(false);
  const [step, setStep] = useState(1);

  useEffect(() => {
    if (!open) return;
    void Promise.all([
      api<Option[]>("/api/v1/branches?limit=100"),
      api<Option[]>("/api/v1/services?limit=100"),
      api<Option[]>("/api/v1/doctors?limit=100"),
      api<Patient[]>("/api/v1/patients?limit=100"),
    ]).then(([b, s, d, p]) => {
      setBranches(b ?? []);
      setServices(s ?? []);
      setDoctors(d ?? []);
      setPatients(p ?? []);
    }).catch(() => undefined);
  }, [open]);

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

      const result = await api<{ reference?: string }>("/api/v1/appointments", {
        method: "POST",
        headers: { ...writeHeaders(), "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify(body),
      });
      toast.success(`Appointment ${result?.reference ?? ""} booked.`);
      onCreated?.();
      onClose();
    } catch (reason) {
      toast.error(reason instanceof Error ? reason.message : "The appointment could not be booked.");
    } finally {
      setBusy(false);
    }
  }

  const canProceed = (s: number) => {
    if (s === 1) return !!form.doctor_id;
    if (s === 2) return true;
    if (s === 3) return !!form.starts_at && !!form.branch_id && !!form.service_id;
    if (s === 4) return form.patient_mode === "existing" ? !!form.patient_id : !!form.full_name.trim();
    return true;
  };

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title="Book appointment"
      subtitle="NEW BOOKING"
      dirty={dirty}
      footer={
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

        {/* Step 1: Select Doctor */}
        {step === 1 && <>
          <p className="eyebrow" style={{ marginBottom: 12 }}>STEP 1 — SELECT DOCTOR</p>
          <div style={{ display: "grid", gap: 8 }}>
            {doctors.map((d) => (
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
            {doctors.length === 0 && <p style={{ color: "var(--muted)", fontSize: 13 }}>No doctors available.</p>}
          </div>
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

        {/* Step 3: Date, Time, Branch, Service */}
        {step === 3 && <>
          <p className="eyebrow" style={{ marginBottom: 12 }}>STEP 3 — DATE & TIME</p>
          <div className="form-grid">
            <label>
              DATE & TIME *
              <input
                type="datetime-local"
                required
                value={form.starts_at}
                onChange={(e) => setForm((f) => ({ ...f, starts_at: e.target.value }))}
              />
            </label>
            <label>
              BRANCH *
              <select required value={form.branch_id} onChange={(e) => setForm((f) => ({ ...f, branch_id: e.target.value }))}>
                <option value="">Select branch</option>
                {branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
              </select>
            </label>
            <label>
              SERVICE *
              <select required value={form.service_id} onChange={(e) => setForm((f) => ({ ...f, service_id: e.target.value }))}>
                <option value="">Select service</option>
                {services.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </label>
          </div>
        </>}

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
          </>}

          {form.patient_mode === "new" && <div className="form-grid">
            <label>FULL NAME *<input required maxLength={160} value={form.full_name} onChange={(e) => setForm((f) => ({ ...f, full_name: e.target.value }))} placeholder="Patient's full name" /></label>
            <label>EMAIL<input type="email" maxLength={320} value={form.email} onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))} placeholder="patient@example.com" /></label>
            <label>PHONE<input maxLength={40} value={form.phone} onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))} placeholder="+92 300 1234567" /></label>
            <div style={{ display: "flex", gap: 8, marginBottom: 4 }}>
              <button type="button" className={`button ${form.dob_mode === "age" ? "button-primary" : "button-secondary"}`} style={{ flex: 1, padding: "6px 10px", fontSize: 11 }} onClick={() => setForm((f) => ({ ...f, dob_mode: "age" as const }))}>Enter age</button>
              <button type="button" className={`button ${form.dob_mode === "dob" ? "button-primary" : "button-secondary"}`} style={{ flex: 1, padding: "6px 10px", fontSize: 11 }} onClick={() => setForm((f) => ({ ...f, dob_mode: "dob" as const }))}>Date of birth</button>
            </div>
            {form.dob_mode === "age"
              ? <label>AGE<input type="number" min={0} max={150} value={form.age} onChange={(e) => setForm((f) => ({ ...f, age: e.target.value }))} placeholder="Years" /></label>
              : <label>DATE OF BIRTH<input type="date" value={form.date_of_birth} onChange={(e) => setForm((f) => ({ ...f, date_of_birth: e.target.value }))} /></label>
            }
          </div>}
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
              <div style={{ display: "flex", justifyContent: "space-between" }}><dt style={{ color: "var(--muted)", fontSize: 11 }}>Doctor</dt><dd style={{ margin: 0 }}>{doctors.find((d) => d.id === form.doctor_id)?.public_name ?? doctors.find((d) => d.id === form.doctor_id)?.name ?? "—"}</dd></div>
              <div style={{ display: "flex", justifyContent: "space-between" }}><dt style={{ color: "var(--muted)", fontSize: 11 }}>Type</dt><dd style={{ margin: 0 }}>{form.appointment_type === "day" ? "☀ Day" : "☽ Evening"}</dd></div>
              <div style={{ display: "flex", justifyContent: "space-between" }}><dt style={{ color: "var(--muted)", fontSize: 11 }}>When</dt><dd style={{ margin: 0 }}>{form.starts_at ? new Date(form.starts_at).toLocaleString(undefined, { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "—"}</dd></div>
              <div style={{ display: "flex", justifyContent: "space-between" }}><dt style={{ color: "var(--muted)", fontSize: 11 }}>Branch</dt><dd style={{ margin: 0 }}>{branches.find((b) => b.id === form.branch_id)?.name ?? "—"}</dd></div>
              <div style={{ display: "flex", justifyContent: "space-between" }}><dt style={{ color: "var(--muted)", fontSize: 11 }}>Patient</dt><dd style={{ margin: 0 }}>{form.patient_mode === "existing" ? (patients.find((p) => p.id === form.patient_id)?.full_name ?? "—") : form.full_name || "—"}</dd></div>
              <div style={{ display: "flex", justifyContent: "space-between" }}><dt style={{ color: "var(--muted)", fontSize: 11 }}>Payment</dt><dd style={{ margin: 0, textTransform: "capitalize" }}>{form.payment_method}</dd></div>
            </dl>
          </div>
        </>}
      </form>
    </Drawer>
  );
}
