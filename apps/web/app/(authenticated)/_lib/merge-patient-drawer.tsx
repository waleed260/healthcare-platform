"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import Drawer from "./drawer";
import { api, apiPage, post, errorMessage } from "./client";
import { useToast } from "./toast";

type Patient = { id: string; full_name: string; patient_number: string; normalized_email: string | null; normalized_phone: string | null };

type Props = {
  open: boolean;
  onClose: () => void;
  sourcePatientId: string;
  sourcePatientName: string;
  onMerged: () => void;
};

export default function MergePatientDrawer({ open, onClose, sourcePatientId, sourcePatientName, onMerged }: Props) {
  const toast = useToast();
  const [search, setSearch] = useState("");
  const [results, setResults] = useState<Patient[]>([]);
  const [searching, setSearching] = useState(false);
  const [targetId, setTargetId] = useState("");
  const [targetName, setTargetName] = useState("");
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) { setSearch(""); setResults([]); setTargetId(""); setTargetName(""); setReason(""); }
  }, [open]);

  const doSearch = useCallback(async () => {
    if (search.trim().length < 2) return;
    setSearching(true);
    try {
      const page = await apiPage<Patient>(`/api/v1/patients?search=${encodeURIComponent(search.trim())}&limit=10`);
      setResults(page.data.filter((p) => p.id !== sourcePatientId));
    } catch (reason) { toast.error(errorMessage(reason, "Patient search failed.")); }
    finally { setSearching(false); }
  }, [search, sourcePatientId, toast]);

  function selectTarget(patient: Patient) {
    setTargetId(patient.id);
    setTargetName(patient.full_name);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!targetId || !reason.trim()) return;
    setSubmitting(true);
    try {
      await post(`/api/v1/patients/${sourcePatientId}/merge`, { target_patient_id: targetId, reason: reason.trim() });
      toast.success(`Merged into ${targetName}. Redirecting…`);
      onMerged();
      onClose();
    } catch (reason) { toast.error(errorMessage(reason, "The merge could not be completed.")); }
    finally { setSubmitting(false); }
  }

  return (
    <Drawer open={open} onClose={onClose} title="Merge patient record">
      <form className="drawer-form" onSubmit={(e) => void submit(e)}>
        <p style={{ fontSize: 13, color: "var(--muted)", margin: "0 0 18px" }}>
          Merge <strong>{sourcePatientName}</strong> into another patient. All records (appointments, notes, documents) move to the target. This cannot be undone.
        </p>

        <label>
          Search for target patient
          <div className="patient-search-row">
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by name, email, or phone"
              onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); void doSearch(); } }}
            />
            <button className="button button-secondary" type="button" onClick={() => void doSearch()} disabled={searching || search.trim().length < 2}>
              {searching ? "…" : "Search"}
            </button>
          </div>
        </label>

        {results.length > 0 && (
          <div className="merge-results">
            {results.map((p) => (
              <button
                key={p.id}
                type="button"
                className={`merge-result-row ${targetId === p.id ? "selected" : ""}`}
                onClick={() => selectTarget(p)}
              >
                <strong>{p.full_name}</strong>
                <small>{p.patient_number} · {p.normalized_email ?? p.normalized_phone ?? "No contact"}</small>
              </button>
            ))}
          </div>
        )}

        {targetId && (
          <div className="merge-target-selected">
            <p className="eyebrow">MERGE TARGET</p>
            <strong>{targetName}</strong>
          </div>
        )}

        <label>
          Reason for merge
          <input required value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Duplicate record, same person" />
        </label>

        <div className="drawer-footer">
          <button className="button button-danger" type="submit" disabled={submitting || !targetId || !reason.trim()}>
            {submitting ? "Merging…" : "Confirm merge"}
          </button>
        </div>
      </form>
    </Drawer>
  );
}
