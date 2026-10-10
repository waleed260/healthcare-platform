"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import Drawer, { useDirty } from "./drawer";
import { useToast } from "./toast";
import { api, writeHeaders } from "./client";

type Option = { id: string; name?: string; public_name?: string };
type Props = {
  open: boolean;
  onClose: () => void;
  clinicSlug: string;
  onCreated?: () => void;
};

export default function AddAppointmentDrawer({ open, onClose, clinicSlug, onCreated }: Props) {
  const toast = useToast();
  const [form, setForm, dirty, resetDirty] = useDirty({
    branch_id: "", service_id: "", doctor_id: "", starts_at: "",
    full_name: "", email: "", phone: "", date_of_birth: "",
  });
  const [branches, setBranches] = useState<Option[]>([]);
  const [services, setServices] = useState<Option[]>([]);
  const [doctors, setDoctors] = useState<Option[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    void Promise.all([
      api<Option[]>("/api/v1/branches?limit=100"),
      api<Option[]>("/api/v1/services?limit=100"),
      api<Option[]>("/api/v1/doctors?limit=100"),
    ]).then(([b, s, d]) => {
      setBranches(b ?? []);
      setServices(s ?? []);
      setDoctors(d ?? []);
    }).catch(() => undefined);
  }, [open]);

  const reset = useCallback(() => {
    setForm(() => ({ branch_id: "", service_id: "", doctor_id: "", starts_at: "", full_name: "", email: "", phone: "", date_of_birth: "" }));
    resetDirty();
  }, [setForm, resetDirty]);

  useEffect(() => { if (!open) reset(); }, [open, reset]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!form.branch_id || !form.service_id || !form.starts_at || !form.full_name.trim()) return;
    setBusy(true);
    try {
      const body: Record<string, unknown> = {
        branch_id: form.branch_id,
        service_id: form.service_id,
        starts_at: new Date(form.starts_at).toISOString(),
        full_name: form.full_name.trim(),
      };
      if (form.doctor_id) body.doctor_id = form.doctor_id;
      if (form.email.trim()) body.email = form.email.trim();
      if (form.phone.trim()) body.phone = form.phone.trim();
      if (form.date_of_birth) body.date_of_birth = form.date_of_birth;

      const result = await api<{ reference?: string }>("/api/v1/public/bookings", {
        method: "POST",
        headers: { ...writeHeaders(), "X-Clinic-Slug": clinicSlug, "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify(body),
      });
      toast.success(`Appointment ${result?.reference ?? ""} created.`);
      onCreated?.();
      onClose();
    } catch (reason) {
      toast.error(reason instanceof Error ? reason.message : "The appointment could not be created.");
    } finally {
      setBusy(false);
    }
  }

  const valid = form.branch_id && form.service_id && form.starts_at && form.full_name.trim();

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title="Add appointment"
      subtitle="NEW BOOKING"
      dirty={dirty}
      footer={
        <>
          <button className="button button-secondary" type="button" onClick={onClose} disabled={busy}>Cancel</button>
          <button className="button button-primary" type="submit" form="add-appointment-form" disabled={busy || !valid}>
            {busy ? "Creating…" : "Book appointment"} <span>→</span>
          </button>
        </>
      }
    >
      <form id="add-appointment-form" className="drawer-form" onSubmit={submit}>
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
        <label>
          DOCTOR
          <select value={form.doctor_id} onChange={(e) => setForm((f) => ({ ...f, doctor_id: e.target.value }))}>
            <option value="">Any available</option>
            {doctors.map((d) => <option key={d.id} value={d.id}>{d.public_name ?? d.name}</option>)}
          </select>
        </label>
        <label>
          DATE & TIME *
          <input
            type="datetime-local"
            required
            value={form.starts_at}
            onChange={(e) => setForm((f) => ({ ...f, starts_at: e.target.value }))}
          />
        </label>

        <p className="eyebrow" style={{ marginTop: 8 }}>PATIENT DETAILS</p>
        <label>
          FULL NAME *
          <input required maxLength={160} value={form.full_name} onChange={(e) => setForm((f) => ({ ...f, full_name: e.target.value }))} placeholder="Patient's full name" />
        </label>
        <label>
          EMAIL
          <input type="email" maxLength={320} value={form.email} onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))} placeholder="patient@example.com" />
        </label>
        <label>
          PHONE
          <input maxLength={40} value={form.phone} onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))} placeholder="+92 300 1234567" />
        </label>
        <label>
          DATE OF BIRTH
          <input type="date" value={form.date_of_birth} onChange={(e) => setForm((f) => ({ ...f, date_of_birth: e.target.value }))} />
        </label>
      </form>
    </Drawer>
  );
}
