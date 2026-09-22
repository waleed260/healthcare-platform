"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

type Patient = { id: string; patient_number: string; full_name: string; normalized_email: string | null; normalized_phone: string | null; date_of_birth: string | null; status: string; version: number };
type Contact = { id: string; contact_type: string; value: string; is_primary: boolean };
type Note = { id: string; note_type: string; visibility: string; body: string; created_at: string };
type CareTeamMember = { doctor_id: string; public_name: string; specialty: string | null; created_at: string };
type Document = { id: string; original_filename: string; mime_type: string; size_bytes: number; scan_status: "pending_scan" | "clean" | "quarantined" | "scan_failed"; retention_class: string; created_at: string; version: number };

async function read(response: Response): Promise<any> {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload?.error?.message ?? "This patient record could not be loaded.");
  return payload.data;
}

function asList<T>(value: unknown): T[] {
  if (Array.isArray(value)) return value as T[];
  if (value && typeof value === "object" && Array.isArray((value as { items?: unknown }).items)) return (value as { items: T[] }).items;
  return [];
}

export default function PatientDetailPage() {
  const { patientId } = useParams<{ patientId: string }>();
  const [patient, setPatient] = useState<Patient | null>(null);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [notes, setNotes] = useState<Note[]>([]);
  const [careTeam, setCareTeam] = useState<CareTeamMember[]>([]);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [documentsError, setDocumentsError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const [patientResponse, contactsResponse, notesResponse, careTeamResponse, documentsResponse] = await Promise.all([fetch(`/api/v1/patients/${patientId}`, { credentials: "include", cache: "no-store" }), fetch(`/api/v1/patients/${patientId}/contacts`, { credentials: "include", cache: "no-store" }), fetch(`/api/v1/patients/${patientId}/notes`, { credentials: "include", cache: "no-store" }), fetch(`/api/v1/patients/${patientId}/care-team`, { credentials: "include", cache: "no-store" }), fetch(`/api/v1/patients/${patientId}/documents`, { credentials: "include", cache: "no-store" })]);
      const [patientData, contactData, noteData, careTeamData] = await Promise.all([read(patientResponse), read(contactsResponse), read(notesResponse), read(careTeamResponse)]);
      setPatient(patientData as Patient); setContacts((contactData ?? []) as Contact[]); setNotes((noteData ?? []) as Note[]); setCareTeam((careTeamData ?? []) as CareTeamMember[]);
      if (documentsResponse.ok) { setDocuments(asList<Document>(await read(documentsResponse))); setDocumentsError(null); }
      else { setDocuments([]); setDocumentsError("Private documents are not available for this role."); }
    } catch (reason) { setError(reason instanceof Error ? reason.message : "This patient record could not be loaded."); }
    finally { setLoading(false); }
  }, [patientId]);
  useEffect(() => { void load(); }, [load]);

  async function downloadDocument(item: Document) {
    setDownloading(item.id); setError(null);
    try {
      const accessResponse = await fetch(`/api/v1/documents/${item.id}/signed-access`, { method: "POST", credentials: "include" });
      const access = await read(accessResponse) as { access_token: string; expires_at: number };
      const response = await fetch(`/api/v1/documents/${item.id}/download`, { credentials: "include", headers: { "X-Document-Access-Token": access.access_token, "X-Document-Expires": String(access.expires_at) } });
      if (!response.ok) throw new Error("The document is not currently available.");
      const blob = await response.blob();
      const link = window.document.createElement("a"); link.href = URL.createObjectURL(blob); link.download = item.original_filename; link.click(); URL.revokeObjectURL(link.href);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "The document could not be downloaded."); }
    finally { setDownloading(null); }
  }

  return <main className="dashboard-page"><header className="dash-header shell"><Link className="wordmark" href="/">care<span>/</span>fully</Link><div className="clinic-chip" aria-label="Clinic workspace session"><span className="clinic-avatar">VC</span><span>Clinic workspace</span></div></header><div className="dashboard shell"><aside className="sidebar"><p className="eyebrow">WORKSPACE</p><nav aria-label="Workspace navigation"><Link className="side-link" href="/dashboard">◈ <span>Overview</span></Link><Link className="side-link active" href="/patients" aria-current="page">○ <span>Patients</span></Link><a className="side-link" href="/dashboard#schedule">◷ <span>Schedule</span></a><a className="side-link" href="/dashboard#followups">↗ <span>Follow-ups</span></a></nav></aside><section className="dash-content patient-content" aria-busy={loading}><Link className="back-link" href="/patients">← Patient directory</Link>{error && <div className="workspace-alert" role="alert"><strong>{error}</strong><button className="ghost-button" type="button" onClick={() => void load()}>Try again <span>→</span></button></div>}{loading && <div className="dashboard-empty" role="status"><strong>Loading authorized record</strong><span>Checking patient scope and related records…</span></div>}{!loading && patient && <><div className="patient-hero"><div className="patient-initial patient-initial-large" aria-hidden="true">{patient.full_name.trim().charAt(0).toUpperCase()}</div><div><p className="eyebrow">PATIENT RECORD · {patient.patient_number}</p><h1>{patient.full_name}</h1><p className="patient-status">{patient.status} · record version {patient.version}</p></div><button className="button button-primary" type="button" onClick={() => void load()}>Refresh <span>↻</span></button></div><div className="detail-grid"><section className="detail-card"><p className="eyebrow">CONTACT</p><h2>Reach them</h2><dl><div><dt>Email</dt><dd>{patient.normalized_email ?? "Not recorded"}</dd></div><div><dt>Phone</dt><dd>{patient.normalized_phone ?? "Not recorded"}</dd></div><div><dt>Date of birth</dt><dd>{patient.date_of_birth ?? "Not recorded"}</dd></div></dl>{contacts.length > 0 && <div className="contact-list">{contacts.map((contact) => <p key={contact.id}><span>{contact.contact_type}</span>{contact.value}{contact.is_primary ? " · primary" : ""}</p>)}</div>}</section><section className="detail-card"><p className="eyebrow">CARE TEAM</p><h2>Assigned clinicians</h2>{careTeam.length === 0 ? <div className="dashboard-empty"><strong>No care-team assignment</strong><span>Only explicitly assigned clinicians can write care-team notes.</span></div> : <div className="care-team-list" role="list">{careTeam.map((member) => <div className="care-team-member" key={member.doctor_id} role="listitem"><span className="care-team-mark" aria-hidden="true">+</span><div><strong>{member.public_name}</strong><small>{member.specialty ?? "Clinician"}</small></div></div>)}</div>}</section><section className="detail-card"><div className="card-heading"><div><p className="eyebrow">AUTHORIZED NOTES</p><h2>Care context</h2></div><span className="directory-count">{notes.length} shown</span></div>{notes.length === 0 ? <div className="dashboard-empty"><strong>No notes available</strong><span>Notes are shown only when your role permits their visibility.</span></div> : <div className="note-list">{notes.map((note) => <article className="note-item" key={note.id}><div><span>{note.note_type} · {note.visibility.replaceAll("_", " ")}</span><time dateTime={note.created_at}>{new Date(note.created_at).toLocaleDateString()}</time></div><p>{note.body}</p></article>)}</div>}</section></div><section className="detail-card document-card"><div className="card-heading"><div><p className="eyebrow">PRIVATE DOCUMENTS</p><h2>Authorized files</h2></div><span className="directory-count">{documents.length} shown</span></div>{documentsError ? <div className="dashboard-empty"><strong>Documents are restricted</strong><span>{documentsError}</span></div> : documents.length === 0 ? <div className="dashboard-empty"><strong>No private documents</strong><span>Files become available only after authorization and a clean scan.</span></div> : <div className="document-list" role="list">{documents.map((item) => <div className="document-row" key={item.id} role="listitem"><div><strong>{item.original_filename}</strong><small>{item.mime_type} · {Math.round(item.size_bytes / 1024)} KB · {item.scan_status.replaceAll("_", " ")}</small></div><button className="button button-secondary" type="button" onClick={() => void downloadDocument(item)} disabled={item.scan_status !== "clean" || downloading !== null}>{downloading === item.id ? "Preparing…" : item.scan_status === "clean" ? "Download" : "Unavailable"}</button></div>)}</div>}</section><p className="privacy-caption detail-privacy">This view is limited by your authenticated clinic and role scope. Private documents are listed without storage keys and downloads require a short-lived, user-bound clean-scan token.</p></>}</section></div></main>;
}
