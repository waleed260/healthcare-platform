"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import Drawer, { useDirty } from "./drawer";
import { useToast } from "./toast";
import { api, post } from "./client";

type Option = { id: string; name?: string; public_name?: string };
type Props = {
  open: boolean;
  onClose: () => void;
  onCreated?: () => void;
};

export default function BlockTimeDrawer({ open, onClose, onCreated }: Props) {
  const toast = useToast();
  const [form, setForm, dirty, resetDirty] = useDirty({ branch_id: "", doctor_id: "", starts_at: "", ends_at: "", reason: "" });
  const [branches, setBranches] = useState<Option[]>([]);
  const [doctors, setDoctors] = useState<Option[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    void Promise.all([
      api<Option[]>("/api/v1/branches?limit=100"),
      api<Option[]>("/api/v1/doctors?limit=100"),
    ]).then(([b, d]) => {
      setBranches(b ?? []);
      setDoctors(d ?? []);
    }).catch(() => undefined);
  }, [open]);

  const reset = useCallback(() => {
    setForm(() => ({ branch_id: "", doctor_id: "", starts_at: "", ends_at: "", reason: "" }));
    resetDirty();
  }, [setForm, resetDirty]);

  useEffect(() => { if (!open) reset(); }, [open, reset]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!form.branch_id || !form.starts_at || !form.ends_at || !form.reason.trim()) return;
    setBusy(true);
    try {
      const body: Record<string, unknown> = {
        branch_id: form.branch_id,
        starts_at: new Date(form.starts_at).toISOString(),
        ends_at: new Date(form.ends_at).toISOString(),
        reason: form.reason.trim(),
      };
      if (form.doctor_id) body.doctor_id = form.doctor_id;
      await post("/api/v1/scheduling/blocked-slots", body, "The time block could not be created.");
      toast.success("Time block created.");
      onCreated?.();
      onClose();
    } catch (reason) {
      toast.error(reason instanceof Error ? reason.message : "The time block could not be created.");
    } finally {
      setBusy(false);
    }
  }

  const valid = form.branch_id && form.starts_at && form.ends_at && form.reason.trim();

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title="Block time"
      subtitle="SCHEDULE BLOCK"
      dirty={dirty}
      footer={
        <>
          <button className="button button-secondary" type="button" onClick={onClose} disabled={busy}>Cancel</button>
          <button className="button button-primary" type="submit" form="block-time-form" disabled={busy || !valid}>
            {busy ? "Blocking…" : "Block time"} <span>→</span>
          </button>
        </>
      }
    >
      <form id="block-time-form" className="drawer-form" onSubmit={submit}>
        <label>
          BRANCH *
          <select required value={form.branch_id} onChange={(e) => setForm((f) => ({ ...f, branch_id: e.target.value }))}>
            <option value="">Select branch</option>
            {branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
          </select>
        </label>
        <label>
          DOCTOR
          <select value={form.doctor_id} onChange={(e) => setForm((f) => ({ ...f, doctor_id: e.target.value }))}>
            <option value="">All doctors (branch-wide)</option>
            {doctors.map((d) => <option key={d.id} value={d.id}>{d.public_name ?? d.name}</option>)}
          </select>
        </label>
        <label>
          STARTS AT *
          <input type="datetime-local" required value={form.starts_at} onChange={(e) => setForm((f) => ({ ...f, starts_at: e.target.value }))} />
        </label>
        <label>
          ENDS AT *
          <input type="datetime-local" required value={form.ends_at} onChange={(e) => setForm((f) => ({ ...f, ends_at: e.target.value }))} />
        </label>
        <label>
          REASON *
          <input required maxLength={500} value={form.reason} onChange={(e) => setForm((f) => ({ ...f, reason: e.target.value }))} placeholder="e.g. Equipment maintenance, staff meeting" />
        </label>
      </form>
    </Drawer>
  );
}
