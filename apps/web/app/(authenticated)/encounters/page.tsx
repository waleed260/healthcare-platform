"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, apiPage, errorMessage, writeHeaders } from "../_lib/client";
import { useToast } from "../_lib/toast";
import { useConfirm } from "../_lib/confirm";
import DataTable, { type Column } from "../_lib/data-table";

type Encounter = {
  id: string; patient_id: string; patient_name: string; appointment_id: string | null;
  doctor_id: string; doctor_name: string; branch_id: string | null;
  encounter_type: string; status: string; chief_complaint: string | null;
  diagnosis: string | null; finalized_at: string | null;
  created_at: string; updated_at: string; version: number;
  token_number: number | null;
};
type Doctor = { id: string; public_name: string };
type Patient = { id: string; full_name: string; mrn: string | null };

const encounterTypes = ["general", "emergency", "dental", "dermatology", "hair", "skin", "follow_up", "procedure"] as const;
const statusLabels: Record<string, string> = {
  all: "All", draft: "Draft", in_progress: "In Progress", ready_for_discharge: "Ready", discharged: "Discharged", finalized: "Finalized", referred: "Referred", transferred: "Transferred",
};
const statusLabel = (v: string) => statusLabels[v] ?? v.charAt(0).toUpperCase() + v.slice(1);
const fmtDate = (v: string) => new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(v));
const fmtDateTime = (v: string) => new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(v));
const typeLabel = (v: string) => v.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
const statusToClass = (s: string) => `pipeline-status status-${s.replaceAll("_", "-")}`;
const filterTabs = ["all", "draft", "in_progress", "ready_for_discharge", "discharged", "finalized"];

export default function EncountersPage() {
  const toast = useToast();
  const confirm = useConfirm();
  const searchParams = useSearchParams();

  const [encounters, setEncounters] = useState<Encounter[]>([]);
  const [doctors, setDoctors] = useState<Doctor[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>("all");
  const [showForm, setShowForm] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());

  const [patientSearch, setPatientSearch] = useState("");
  const [patientResults, setPatientResults] = useState<Patient[]>([]);
  const [selectedPatient, setSelectedPatient] = useState<Patient | null>(null);
  const [selectedDoctor, setSelectedDoctor] = useState("");
  const [encType, setEncType] = useState<string>("general");
  const [complaint, setComplaint] = useState("");
  const [appointmentId, setAppointmentId] = useState<string | null>(null);

  const startHandled = useRef(false);
  useEffect(() => {
    if (startHandled.current) return;
    if (searchParams.get("start") !== "1") return;
    startHandled.current = true;
    setShowForm(true);
    const apptId = searchParams.get("appointment_id");
    const doctorId = searchParams.get("doctor_id");
    const patientId = searchParams.get("patient_id");
    const type = searchParams.get("type");
    if (apptId) setAppointmentId(apptId);
    if (doctorId) setSelectedDoctor(doctorId);
    if (type && encounterTypes.includes(type as typeof encounterTypes[number])) setEncType(type);
    if (patientId) {
      void api<Patient>(`/api/v1/patients/${patientId}`).then((p) => {
        if (p) setSelectedPatient(p);
      }).catch(() => {});
    }
  }, [searchParams]);

  const loadEncounters = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ limit: "100" });
      if (filter !== "all") params.set("status", filter);
      const page = await apiPage<Encounter>(`/api/v1/encounters?${params.toString()}`);
      setEncounters(page.data);
    } catch (reason) {
      setError(errorMessage(reason, "Could not load encounters."));
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => { void loadEncounters(); }, [loadEncounters]);

  useEffect(() => {
    void api<Doctor[]>("/api/v1/doctors?limit=100").then((d) => setDoctors(d ?? [])).catch(() => {});
  }, []);

  async function searchPatients(q: string) {
    setPatientSearch(q);
    if (q.length < 2) { setPatientResults([]); return; }
    try {
      const rows = await api<Patient[]>(`/api/v1/patients?search=${encodeURIComponent(q)}&limit=10`);
      setPatientResults(rows ?? []);
    } catch { setPatientResults([]); }
  }

  async function createEncounter(e: FormEvent) {
    e.preventDefault();
    if (!selectedPatient) { toast.error("Select a patient."); return; }
    if (!selectedDoctor) { toast.error("Select a doctor."); return; }
    setBusy("create");
    try {
      const body: Record<string, unknown> = { patient_id: selectedPatient.id, doctor_id: selectedDoctor, encounter_type: encType };
      if (complaint.trim()) body.chief_complaint = complaint.trim();
      if (appointmentId) body.appointment_id = appointmentId;
      const result = await api<{ id: string }>("/api/v1/encounters", { method: "POST", headers: writeHeaders(), body: JSON.stringify(body) });
      toast.success("Encounter created.");
      setShowForm(false); setSelectedPatient(null); setPatientSearch(""); setComplaint(""); setAppointmentId(null);
      if (result?.id) { window.location.href = `/encounters/${result.id}`; } else { await loadEncounters(); }
    } catch (reason) { toast.error(errorMessage(reason, "Could not create encounter.")); }
    finally { setBusy(null); }
  }

  async function deleteEncounter(enc: Encounter) {
    const yes = await confirm({ message: `Delete encounter for ${enc.patient_name}?`, danger: true });
    if (!yes) return;
    setBusy(enc.id);
    try {
      await api(`/api/v1/encounters/${enc.id}`, { method: "DELETE", headers: writeHeaders() });
      toast.success("Encounter removed.");
      await loadEncounters();
    } catch (reason) { toast.error(errorMessage(reason, "Could not delete.")); }
    finally { setBusy(null); }
  }

  async function bulkDeleteDrafts() {
    const drafts = encounters.filter((e) => e.status === "draft" && selectedKeys.has(e.id));
    if (drafts.length === 0) { toast.error("No draft encounters selected."); return; }
    const yes = await confirm({ message: `Delete ${drafts.length} draft encounter${drafts.length === 1 ? "" : "s"}?`, danger: true });
    if (!yes) return;
    setBusy("bulk");
    let done = 0;
    for (const enc of drafts) {
      try {
        await api(`/api/v1/encounters/${enc.id}`, { method: "DELETE", headers: writeHeaders() });
        done++;
      } catch { /* continue */ }
    }
    setBusy(null);
    setSelectedKeys(new Set());
    toast.success(`${done} draft${done === 1 ? "" : "s"} deleted.`);
    await loadEncounters();
  }

  const counts: Record<string, number> = {};
  for (const e of encounters) counts[e.status] = (counts[e.status] ?? 0) + 1;

  const filtered = useMemo(() => {
    if (!searchQuery.trim()) return encounters;
    const q = searchQuery.toLowerCase();
    return encounters.filter((e) =>
      e.patient_name.toLowerCase().includes(q) ||
      e.doctor_name.toLowerCase().includes(q) ||
      (e.chief_complaint && e.chief_complaint.toLowerCase().includes(q)) ||
      (e.diagnosis && e.diagnosis.toLowerCase().includes(q))
    );
  }, [encounters, searchQuery]);

  const encCols: Column<Encounter>[] = useMemo(() => [
    { key: "patient", header: "Patient", width: "1fr", sortable: true, sortFn: (a, b) => a.patient_name.localeCompare(b.patient_name), render: (enc) => (
      <div className="enc-cell-main">
        <div className="enc-cell-top">
          {enc.token_number != null && <span className="enc-token">#{enc.token_number}</span>}
          <Link href={`/encounters/${enc.id}`} className="enc-patient-link">{enc.patient_name}</Link>
          <span className={statusToClass(enc.status)}>{statusLabel(enc.status)}</span>
          <span className="enc-type">{typeLabel(enc.encounter_type)}</span>
        </div>
        {enc.chief_complaint && <p className="enc-complaint">{enc.chief_complaint.slice(0, 100)}</p>}
        <div className="enc-meta">
          <span>Dr. {enc.doctor_name}</span>
          {enc.diagnosis && <span>Dx: {enc.diagnosis.slice(0, 40)}</span>}
          <span>{fmtDateTime(enc.created_at)}</span>
          {enc.finalized_at && <span>Finalized {fmtDate(enc.finalized_at)}</span>}
        </div>
      </div>
    )},
    { key: "actions", header: "Actions", width: "auto", srOnly: true, render: (enc) => (
      <div className="enc-actions">
        <Link className="button button-secondary enc-action-btn" href={`/encounters/${enc.id}`}>{["finalized", "discharged"].includes(enc.status) ? "View" : "Edit"}</Link>
        {!["finalized", "discharged"].includes(enc.status) && (
          <button className="ghost-button enc-action-btn danger-control" type="button" onClick={() => void deleteEncounter(enc)}>Delete</button>
        )}
      </div>
    )},
  ], []);

  return (
    <main className="dash-content">
      <div className="dash-topline">
        <div>
          <h1>Encounters</h1>
        </div>
        <div className="header-actions">
          <button className="button button-primary" type="button" onClick={() => setShowForm((v) => !v)}>{showForm ? "Close" : "New encounter"} <span>＋</span></button>
        </div>
      </div>

      {error && <div className="workspace-alert" role="alert"><strong>{error}</strong></div>}

      <div className="billing-summary">
        <div><span className="eyebrow">DRAFTS</span><strong className={counts.draft ? "enc-count-warn" : ""}>{counts.draft ?? 0}</strong></div>
        <div><span className="eyebrow">IN PROGRESS</span><strong>{counts.in_progress ?? 0}</strong></div>
        <div><span className="eyebrow">DISCHARGED</span><strong>{counts.discharged ?? 0}</strong></div>
        <div><span className="eyebrow">TOTAL</span><strong>{encounters.length}</strong></div>
      </div>

      <div className="pipeline-toolbar">
        <div className="pipeline-tabs" role="tablist">
          {filterTabs.map((s) => (
            <button key={s} className={filter === s ? "active" : ""} onClick={() => setFilter(s)}>{statusLabel(s)}</button>
          ))}
        </div>
        <input type="search" className="enc-search" value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} placeholder="Search patient, doctor, complaint…" />
      </div>

      {showForm && (
        <form className="surface-card enc-form" onSubmit={(e) => void createEncounter(e)}>
          <div className="surface-card-heading"><div><p className="eyebrow">NEW ENCOUNTER</p><h2>Start documentation</h2></div></div>
          <div className="form-grid">
            <label>
              Patient *
              {selectedPatient ? (
                <div className="enc-selected-patient">
                  <strong>{selectedPatient.full_name}</strong>
                  {selectedPatient.mrn && <span className="enc-mrn">MRN: {selectedPatient.mrn}</span>}
                  <button className="ghost-button" type="button" onClick={() => { setSelectedPatient(null); setPatientSearch(""); }}>Change</button>
                </div>
              ) : (
                <>
                  <input value={patientSearch} onChange={(e) => void searchPatients(e.target.value)} placeholder="Search patient by name…" />
                  {patientResults.length > 0 && (
                    <div className="enc-patient-dropdown">
                      <div className="enc-dropdown-hint">Click to select:</div>
                      {patientResults.map((p) => (
                        <button key={p.id} type="button" className="enc-dropdown-item" onClick={() => { setSelectedPatient(p); setPatientResults([]); }}>
                          {p.full_name} {p.mrn && <span className="enc-mrn">· {p.mrn}</span>}
                        </button>
                      ))}
                    </div>
                  )}
                  {patientSearch.length >= 2 && patientResults.length === 0 && (
                    <span className="enc-no-results">No patients found for &ldquo;{patientSearch}&rdquo;</span>
                  )}
                </>
              )}
            </label>
            <label>Doctor *
              <select required value={selectedDoctor} onChange={(e) => setSelectedDoctor(e.target.value)}>
                <option value="">Select doctor</option>
                {doctors.map((d) => <option key={d.id} value={d.id}>{d.public_name}</option>)}
              </select>
            </label>
            <label>Type
              <select value={encType} onChange={(e) => setEncType(e.target.value)}>
                {encounterTypes.map((t) => <option key={t} value={t}>{typeLabel(t)}</option>)}
              </select>
            </label>
            <label className="enc-full-width">Chief complaint<textarea value={complaint} onChange={(e) => setComplaint(e.target.value)} placeholder="Patient's chief complaint" rows={2} /></label>
          </div>
          <div className="form-actions"><button className="button button-primary" type="submit" disabled={busy === "create"}>{busy === "create" ? "Creating…" : "Create encounter"}</button></div>
        </form>
      )}

      <section className="surface-card">
        <div className="surface-card-heading"><div><h2>{filter === "all" ? "All encounters" : statusLabel(filter)}</h2></div><span className="muted-mono">{filtered.length} RECORDS</span></div>
        <DataTable
          columns={encCols}
          rows={filtered}
          rowKey={(e) => e.id}
          loading={loading}
          skeletonRows={5}
          selectable
          selectedKeys={selectedKeys}
          onSelectionChange={setSelectedKeys}
          emptyTitle={searchQuery ? "No matching encounters" : "No encounters"}
          emptyBody={searchQuery ? "Try a different search." : "Create one to start documenting."}
        />
        {selectedKeys.size > 0 && (
          <div className="bulk-bar">
            <strong>{selectedKeys.size} selected</strong>
            <button type="button" disabled={busy === "bulk"} onClick={() => void bulkDeleteDrafts()}>{busy === "bulk" ? "Deleting…" : "Delete drafts"}</button>
            <button type="button" onClick={() => setSelectedKeys(new Set())}>Clear</button>
          </div>
        )}
      </section>
    </main>
  );
}
