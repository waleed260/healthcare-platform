"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import Drawer, { useDirty } from "./drawer";
import { useToast } from "./toast";
import { post, api } from "./client";

type Duplicate = { id: string; full_name: string; normalized_email: string | null; normalized_phone: string | null; score: number };
type Patient = { id: string; patient_number: string; full_name: string };

type Props = {
  open: boolean;
  onClose: () => void;
  onCreated?: (patient: Patient) => void;
};

export default function AddPatientDrawer({ open, onClose, onCreated }: Props) {
  const toast = useToast();
  const [form, setForm, dirty, resetDirty] = useDirty({ full_name: "", email: "", phone: "", date_of_birth: "" });
  const [duplicates, setDuplicates] = useState<Duplicate[]>([]);
  const [busy, setBusy] = useState(false);
  const [checking, setChecking] = useState(false);

  const reset = useCallback(() => {
    setForm(() => ({ full_name: "", email: "", phone: "", date_of_birth: "" }));
    resetDirty();
    setDuplicates([]);
  }, [setForm, resetDirty]);

  useEffect(() => { if (!open) reset(); }, [open, reset]);

  const checkDuplicates = useCallback(async () => {
    if (!form.full_name.trim()) return;
    setChecking(true);
    try {
      const body: Record<string, string> = { full_name: form.full_name.trim() };
      if (form.email.trim()) body.email = form.email.trim();
      if (form.phone.trim()) body.phone = form.phone.trim();
      if (form.date_of_birth) body.date_of_birth = form.date_of_birth;
      const result = await post<Duplicate[]>("/api/v1/patients/duplicate-candidates", body, "Could not check for duplicates.");
      setDuplicates(result ?? []);
    } catch {
      setDuplicates([]);
    } finally {
      setChecking(false);
    }
  }, [form]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!form.full_name.trim()) return;
    setBusy(true);
    try {
      const body: Record<string, string> = { full_name: form.full_name.trim() };
      if (form.email.trim()) body.email = form.email.trim();
      if (form.phone.trim()) body.phone = form.phone.trim();
      if (form.date_of_birth) body.date_of_birth = form.date_of_birth;
      const patient = await post<Patient>("/api/v1/patients", body, "The patient could not be created.");
      toast.success(`Patient "${patient.full_name}" created.`);
      onCreated?.(patient);
      onClose();
    } catch (reason) {
      toast.error(reason instanceof Error ? reason.message : "The patient could not be created.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title="Add patient"
      subtitle="NEW RECORD"
      dirty={dirty}
      footer={
        <>
          <button className="button button-secondary" type="button" onClick={onClose} disabled={busy}>Cancel</button>
          <button className="button button-primary" type="submit" form="add-patient-form" disabled={busy || !form.full_name.trim()}>
            {busy ? "Creating…" : "Create patient"} <span>→</span>
          </button>
        </>
      }
    >
      <form id="add-patient-form" className="drawer-form" onSubmit={submit}>
        <label>
          FULL NAME *
          <input
            required
            maxLength={200}
            value={form.full_name}
            onChange={(e) => setForm((f) => ({ ...f, full_name: e.target.value }))}
            onBlur={checkDuplicates}
            placeholder="Patient's full name"
            autoFocus
          />
        </label>
        <label>
          EMAIL
          <input
            type="email"
            maxLength={320}
            value={form.email}
            onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
            onBlur={checkDuplicates}
            placeholder="patient@example.com"
          />
        </label>
        <label>
          PHONE
          <input
            maxLength={40}
            value={form.phone}
            onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))}
            onBlur={checkDuplicates}
            placeholder="+92 300 1234567"
          />
        </label>
        <label>
          DATE OF BIRTH
          <input
            type="date"
            value={form.date_of_birth}
            onChange={(e) => setForm((f) => ({ ...f, date_of_birth: e.target.value }))}
            onBlur={checkDuplicates}
          />
        </label>

        {checking && <p className="drawer-note">Checking for duplicates…</p>}
        {duplicates.length > 0 && (
          <div className="duplicate-warning">
            <p className="eyebrow">POSSIBLE DUPLICATES</p>
            {duplicates.map((d) => (
              <div key={d.id} className="duplicate-row">
                <strong>{d.full_name}</strong>
                <small>{d.normalized_email ?? d.normalized_phone ?? "No contact"} · {Math.round(d.score * 100)}% match</small>
              </div>
            ))}
          </div>
        )}
      </form>
    </Drawer>
  );
}
