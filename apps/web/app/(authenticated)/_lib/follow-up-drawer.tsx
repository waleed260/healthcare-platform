"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import Drawer, { useDirty } from "./drawer";
import { useToast } from "./toast";
import { api, post } from "./client";

type Option = { id: string; name?: string; full_name?: string; public_name?: string };
type Props = {
  open: boolean;
  onClose: () => void;
  patientId?: string;
  appointmentId?: string;
  onCreated?: () => void;
};

export default function FollowUpDrawer({ open, onClose, patientId, appointmentId, onCreated }: Props) {
  const toast = useToast();
  const [form, setForm, dirty, resetDirty] = useDirty({
    patient_id: patientId ?? "",
    appointment_id: appointmentId ?? "",
    assignee_user_id: "",
    reason: "",
    due_at: "",
    priority: "normal",
  });
  const [patients, setPatients] = useState<Option[]>([]);
  const [staff, setStaff] = useState<Option[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    void Promise.all([
      patientId ? Promise.resolve([]) : api<Option[]>("/api/v1/patients?limit=100"),
      api<Option[]>("/api/v1/staff?limit=100").catch(() => []),
    ]).then(([p, s]) => {
      setPatients(p ?? []);
      setStaff(s ?? []);
    }).catch(() => undefined);
  }, [open, patientId]);

  const reset = useCallback(() => {
    setForm(() => ({
      patient_id: patientId ?? "",
      appointment_id: appointmentId ?? "",
      assignee_user_id: "",
      reason: "",
      due_at: "",
      priority: "normal",
    }));
    resetDirty();
  }, [setForm, resetDirty, patientId, appointmentId]);

  useEffect(() => { if (!open) reset(); }, [open, reset]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!form.patient_id || !form.reason.trim() || !form.due_at) return;
    setBusy(true);
    try {
      const body: Record<string, unknown> = {
        patient_id: form.patient_id,
        reason: form.reason.trim(),
        due_at: new Date(form.due_at).toISOString(),
        priority: form.priority,
      };
      if (form.appointment_id) body.appointment_id = form.appointment_id;
      if (form.assignee_user_id) body.assignee_user_id = form.assignee_user_id;
      await post("/api/v1/operations/follow-ups", body, "The follow-up could not be created.");
      toast.success("Follow-up created.");
      onCreated?.();
      onClose();
    } catch (reason) {
      toast.error(reason instanceof Error ? reason.message : "The follow-up could not be created.");
    } finally {
      setBusy(false);
    }
  }

  const valid = form.patient_id && form.reason.trim() && form.due_at;

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title="Create follow-up"
      subtitle="TASK"
      dirty={dirty}
      footer={
        <>
          <button className="button button-secondary" type="button" onClick={onClose} disabled={busy}>Cancel</button>
          <button className="button button-primary" type="submit" form="follow-up-form" disabled={busy || !valid}>
            {busy ? "Creating…" : "Create follow-up"} <span>→</span>
          </button>
        </>
      }
    >
      <form id="follow-up-form" className="drawer-form" onSubmit={submit}>
        {!patientId && (
          <label>
            PATIENT *
            <select required value={form.patient_id} onChange={(e) => setForm((f) => ({ ...f, patient_id: e.target.value }))}>
              <option value="">Select patient</option>
              {patients.map((p) => <option key={p.id} value={p.id}>{p.full_name ?? p.name}</option>)}
            </select>
          </label>
        )}
        <label>
          REASON *
          <textarea
            required
            maxLength={500}
            value={form.reason}
            onChange={(e) => setForm((f) => ({ ...f, reason: e.target.value }))}
            placeholder="What needs to be followed up?"
            rows={3}
          />
        </label>
        <label>
          DUE DATE & TIME *
          <input type="datetime-local" required value={form.due_at} onChange={(e) => setForm((f) => ({ ...f, due_at: e.target.value }))} />
        </label>
        <label>
          PRIORITY
          <select value={form.priority} onChange={(e) => setForm((f) => ({ ...f, priority: e.target.value }))}>
            <option value="low">Low</option>
            <option value="normal">Normal</option>
            <option value="high">High</option>
          </select>
        </label>
        <label>
          ASSIGN TO
          <select value={form.assignee_user_id} onChange={(e) => setForm((f) => ({ ...f, assignee_user_id: e.target.value }))}>
            <option value="">Unassigned</option>
            {staff.map((s) => <option key={s.id} value={s.id}>{s.public_name ?? s.name ?? s.full_name}</option>)}
          </select>
        </label>
      </form>
    </Drawer>
  );
}
