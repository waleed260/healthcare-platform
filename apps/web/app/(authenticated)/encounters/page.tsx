"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import anime from "animejs";
import { api, apiPage, errorMessage, writeHeaders } from "../_lib/client";
import { useToast } from "../_lib/toast";
import { useConfirm } from "../_lib/confirm";

type Encounter = {
  id: string; patient_id: string; patient_name: string; appointment_id: string | null;
  doctor_id: string; doctor_name: string; branch_id: string | null;
  encounter_type: string; status: string; chief_complaint: string | null;
  diagnosis: string | null; finalized_at: string | null;
  created_at: string; updated_at: string; version: number;
};
type Doctor = { id: string; public_name: string };
type Patient = { id: string; full_name: string; mrn: string | null };

const encounterTypes = ["general", "emergency", "dental", "dermatology", "hair", "skin", "follow_up", "procedure"] as const;
const statusLabel = (v: string) => v === "in_review" ? "In Review" : v.charAt(0).toUpperCase() + v.slice(1);
const fmtDate = (v: string) => new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(v));
const fmtDateTime = (v: string) => new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(v));
const typeLabel = (v: string) => v.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
const statusColor: Record<string, string> = { draft: "#e0a458", in_review: "var(--accent)", finalized: "var(--leaf)" };

export default function EncountersPage() {
  const toast = useToast();
  const confirm = useConfirm();

  const [encounters, setEncounters] = useState<Encounter[]>([]);
  const [doctors, setDoctors] = useState<Doctor[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>("all");
  const [showForm, setShowForm] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);

  const [patientSearch, setPatientSearch] = useState("");
  const [patientResults, setPatientResults] = useState<Patient[]>([]);
  const [selectedPatient, setSelectedPatient] = useState<Patient | null>(null);
  const [selectedDoctor, setSelectedDoctor] = useState("");
  const [encType, setEncType] = useState<string>("general");
  const [complaint, setComplaint] = useState("");

  const loadEncounters = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ limit: "100" });
      if (filter !== "all") params.set("status", filter);
      const [page, docs] = await Promise.all([
        apiPage<Encounter>(`/api/v1/encounters?${params.toString()}`),
        api<Doctor[]>("/api/v1/doctors?limit=100").catch(() => []),
      ]);
      setEncounters(page.data);
      setDoctors(docs ?? []);
    } catch (reason) {
      setError(errorMessage(reason, "Could not load encounters."));
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => { void loadEncounters(); }, [loadEncounters]);

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
    if (!selectedPatient || !selectedDoctor) return;
    setBusy("create");
    try {
      const body: Record<string, unknown> = {
        patient_id: selectedPatient.id,
        doctor_id: selectedDoctor,
        encounter_type: encType,
      };
      if (complaint.trim()) body.chief_complaint = complaint.trim();
      const result = await api<{ id: string }>("/api/v1/encounters", { method: "POST", headers: writeHeaders(), body: JSON.stringify(body) });
      toast.success("Encounter created.");
      setShowForm(false);
      setSelectedPatient(null);
      setPatientSearch("");
      setComplaint("");
      if (result?.id) {
        window.location.href = `/encounters/${result.id}`;
      } else {
        await loadEncounters();
      }
    } catch (reason) {
      toast.error(errorMessage(reason, "Could not create encounter."));
    } finally {
      setBusy(null);
    }
  }

  async function deleteEncounter(enc: Encounter) {
    const yes = await confirm({ message: `Delete encounter for ${enc.patient_name}?`, danger: true });
    if (!yes) return;
    setBusy(enc.id);
    try {
      await api(`/api/v1/encounters/${enc.id}`, { method: "DELETE", headers: writeHeaders() });
      toast.success("Encounter removed.");
      await loadEncounters();
    } catch (reason) {
      toast.error(errorMessage(reason, "Could not delete."));
    } finally {
      setBusy(null);
    }
  }

  const listRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (loading || encounters.length === 0 || !listRef.current) return;
    anime({ targets: listRef.current.querySelectorAll(".enc-row"), opacity: [0, 1], translateY: [16, 0], duration: 400, delay: anime.stagger(30, { start: 60 }), easing: "easeOutCubic" });
  }, [loading, encounters.length]);

  const drafts = encounters.filter((e) => e.status === "draft").length;
  const reviews = encounters.filter((e) => e.status === "in_review").length;
  const finalized = encounters.filter((e) => e.status === "finalized").length;

  return (
    <section className="dash-content">
      <div className="dash-topline">
        <div>
          <p className="eyebrow">CLINICAL · DOCUMENTATION</p>
          <h1>Encounter <em>forms.</em></h1>
        </div>
        <div className="header-actions">
          <button className="button button-primary" type="button" onClick={() => setShowForm((v) => !v)}>{showForm ? "Close" : "New encounter"} <span>＋</span></button>
        </div>
      </div>

      {error && <div className="workspace-alert" role="alert"><strong>{error}</strong></div>}

      <div className="billing-summary">
        <div><span className="eyebrow">DRAFTS</span><strong style={{ color: drafts > 0 ? "#e0a458" : undefined }}>{drafts}</strong></div>
        <div><span className="eyebrow">IN REVIEW</span><strong>{reviews}</strong></div>
        <div><span className="eyebrow">FINALIZED</span><strong>{finalized}</strong></div>
        <div><span className="eyebrow">TOTAL</span><strong>{encounters.length}</strong></div>
      </div>

      <div className="pipeline-toolbar">
        <div className="pipeline-tabs" role="tablist">
          {["all", "draft", "in_review", "finalized"].map((s) => (
            <button key={s} className={filter === s ? "active" : ""} onClick={() => setFilter(s)}>{statusLabel(s === "all" ? "all" : s)}</button>
          ))}
        </div>
      </div>

      {showForm && (
        <form className="surface-card" style={{ marginBottom: 16 }} onSubmit={(e) => void createEncounter(e)}>
          <div className="surface-card-heading"><div><p className="eyebrow">NEW ENCOUNTER</p><h2>Start clinical documentation</h2></div></div>
          <div className="form-grid">
            <label>
              Patient *
              {selectedPatient ? (
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <strong style={{ fontSize: 13 }}>{selectedPatient.full_name}</strong>
                  {selectedPatient.mrn && <span style={{ fontSize: 11, color: "var(--muted)" }}>MRN: {selectedPatient.mrn}</span>}
                  <button className="ghost-button" type="button" style={{ fontSize: 11, color: "var(--coral)" }} onClick={() => { setSelectedPatient(null); setPatientSearch(""); }}>Change</button>
                </div>
              ) : (
                <>
                  <input value={patientSearch} onChange={(e) => void searchPatients(e.target.value)} placeholder="Search patient by name…" />
                  {patientResults.length > 0 && (
                    <div style={{ border: "1px solid var(--line)", borderRadius: 6, maxHeight: 150, overflowY: "auto", marginTop: 4 }}>
                      {patientResults.map((p) => (
                        <button key={p.id} type="button" style={{ display: "block", width: "100%", textAlign: "left", padding: "8px 12px", fontSize: 12, background: "none", border: "none", borderBottom: "1px solid var(--line)", cursor: "pointer", color: "var(--fg)" }} onClick={() => { setSelectedPatient(p); setPatientResults([]); }}>
                          {p.full_name} {p.mrn && <span style={{ color: "var(--muted)" }}>· {p.mrn}</span>}
                        </button>
                      ))}
                    </div>
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
            <label style={{ gridColumn: "1 / -1" }}>Chief complaint<textarea value={complaint} onChange={(e) => setComplaint(e.target.value)} placeholder="Patient's chief complaint" rows={2} style={{ width: "100%", resize: "vertical" }} /></label>
          </div>
          <div className="form-actions"><button className="button button-primary" type="submit" disabled={busy === "create" || !selectedPatient || !selectedDoctor}>{busy === "create" ? "Creating…" : "Create encounter"}</button></div>
        </form>
      )}

      <section className="surface-card">
        <div className="surface-card-heading"><div><p className="eyebrow">ENCOUNTERS</p><h2>{filter === "all" ? "All encounters" : statusLabel(filter)}</h2></div><span className="muted-mono">{encounters.length} RECORDS</span></div>

        {loading && <div className="dashboard-empty" role="status"><strong>Loading encounters…</strong></div>}
        {!loading && encounters.length === 0 && <div className="dashboard-empty"><strong>No encounters</strong><span>Create an encounter to start documenting.</span></div>}

        {!loading && encounters.length > 0 && (
          <div ref={listRef}>
            {encounters.map((enc) => (
              <div className="enc-row" key={enc.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "14px 0", borderBottom: "1px solid var(--line)", gap: 12 }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                    <Link href={`/encounters/${enc.id}`} style={{ fontSize: 13, fontWeight: 600, color: "var(--fg)" }}>{enc.patient_name}</Link>
                    <span style={{ fontSize: 11, padding: "1px 8px", borderRadius: 10, background: statusColor[enc.status] ?? "var(--line)", color: "#fff" }}>{statusLabel(enc.status)}</span>
                    <span style={{ fontSize: 10, color: "var(--muted)", background: "var(--line)", padding: "1px 6px", borderRadius: 4 }}>{typeLabel(enc.encounter_type)}</span>
                  </div>
                  {enc.chief_complaint && <p style={{ margin: "4px 0 0", fontSize: 12, color: "var(--muted)" }}>{enc.chief_complaint.slice(0, 100)}</p>}
                  <div style={{ display: "flex", gap: 12, marginTop: 4, fontSize: 11, color: "var(--muted)" }}>
                    <span>Dr. {enc.doctor_name}</span>
                    {enc.diagnosis && <span>Dx: {enc.diagnosis.slice(0, 40)}</span>}
                    <span>{fmtDateTime(enc.created_at)}</span>
                    {enc.finalized_at && <span>Finalized {fmtDate(enc.finalized_at)}</span>}
                  </div>
                </div>
                <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
                  <Link className="button button-secondary" href={`/encounters/${enc.id}`} style={{ fontSize: 11, padding: "4px 10px" }}>{enc.status === "finalized" ? "View" : "Edit"}</Link>
                  {enc.status !== "finalized" && (
                    <button className="ghost-button" style={{ fontSize: 10, color: "var(--coral)", padding: "2px 6px" }} type="button" onClick={() => void deleteEncounter(enc)}>Delete</button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </section>
  );
}
