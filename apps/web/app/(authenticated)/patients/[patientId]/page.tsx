"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, apiPage, csrfToken, errorMessage } from "../../_lib/client";
import { useToast } from "../../_lib/toast";
import { useConfirm } from "../../_lib/confirm";
import MergePatientDrawer from "../../_lib/merge-patient-drawer";

type Patient = { id: string; patient_number: string; full_name: string; normalized_email: string | null; normalized_phone: string | null; date_of_birth: string | null; status: string; version: number };
type Contact = { id: string; contact_type: string; value: string; is_primary: boolean };
type Note = { id: string; note_type: string; visibility: string; body: string; created_at: string };
type CareTeamMember = { doctor_id: string; public_name: string; specialty: string | null; created_at: string };
type Document = { id: string; original_filename: string; mime_type: string; size_bytes: number; scan_status: string; retention_class: string; created_at: string; version: number };
type HistoryEvent = { id: string; event_type: string; entity_id: string; from_status: string | null; to_status: string | null; reason: string | null; actor_user_id: string | null; created_at: string };
type Appointment = { id: string; reference: string; starts_at: string; ends_at: string; status: string; doctor_id: string | null; service_id: string | null };
type Consent = { id: string; consent_type: string; status: string; version: string; created_at: string };
type Prescription = { id: string; medication_name: string; dosage: string; frequency: string; duration_days: number | null; status: string; created_at: string };
type Invoice = { id: string; invoice_number: string; total_minor: number; paid_minor: number; status: string; issued_at: string; currency: string };

type Tab = "overview" | "timeline" | "appointments" | "notes" | "documents" | "consents" | "prescriptions" | "invoices";
const tabs: { key: Tab; label: string }[] = [
  { key: "overview", label: "Overview" },
  { key: "timeline", label: "Timeline" },
  { key: "appointments", label: "Appointments" },
  { key: "notes", label: "Notes" },
  { key: "documents", label: "Documents" },
  { key: "consents", label: "Consents" },
  { key: "prescriptions", label: "Prescriptions" },
  { key: "invoices", label: "Invoices" },
];

const statusLabel = (s: string) => s.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
const formatDate = (v: string) => new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(v));
const formatDateTime = (v: string) => new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(v));
const formatTime = (v: string) => new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(new Date(v));
const money = (minor: number, currency = "PKR") => new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: 0 }).format(minor / 100);

export default function PatientDetailPage() {
  const { patientId } = useParams<{ patientId: string }>();
  const toast = useToast();
  const confirm = useConfirm();

  const [patient, setPatient] = useState<Patient | null>(null);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [careTeam, setCareTeam] = useState<CareTeamMember[]>([]);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>("overview");

  // Edit state
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editName, setEditName] = useState("");
  const [editEmail, setEditEmail] = useState("");
  const [editPhone, setEditPhone] = useState("");
  const [editDob, setEditDob] = useState("");

  // Tab data states
  const [notes, setNotes] = useState<Note[]>([]);
  const [notesCursor, setNotesCursor] = useState<string | null>(null);
  const [notesLoaded, setNotesLoaded] = useState(false);
  const [history, setHistory] = useState<HistoryEvent[]>([]);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [appointmentsLoaded, setAppointmentsLoaded] = useState(false);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [documentsError, setDocumentsError] = useState<string | null>(null);
  const [documentsLoaded, setDocumentsLoaded] = useState(false);
  const [consents, setConsents] = useState<Consent[]>([]);
  const [consentsLoaded, setConsentsLoaded] = useState(false);
  const [prescriptions, setPrescriptions] = useState<Prescription[]>([]);
  const [prescriptionsLoaded, setPrescriptionsLoaded] = useState(false);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [invoicesLoaded, setInvoicesLoaded] = useState(false);
  const [downloading, setDownloading] = useState<string | null>(null);
  const [mergeOpen, setMergeOpen] = useState(false);

  const can = (p: string) => permissions.includes(p);

  const loadCore = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [session, patientData, contactData, careTeamData] = await Promise.all([
        api<{ permissions?: string[] }>("/api/v1/auth/me"),
        api<Patient>(`/api/v1/patients/${patientId}`),
        api<Contact[]>(`/api/v1/patients/${patientId}/contacts`),
        api<CareTeamMember[]>(`/api/v1/patients/${patientId}/care-team`),
      ]);
      setPermissions(session.permissions ?? []);
      setPatient(patientData);
      setContacts(contactData ?? []);
      setCareTeam(careTeamData ?? []);
    } catch (reason) {
      setError(errorMessage(reason, "This patient record could not be loaded."));
    } finally {
      setLoading(false);
    }
  }, [patientId]);

  useEffect(() => { void loadCore(); }, [loadCore]);

  // Lazy-load tab data
  const loadNotes = useCallback(async (cursor: string | null = null) => {
    try {
      const url = `/api/v1/patients/${patientId}/notes${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ""}`;
      const page = await apiPage<Note>(url);
      setNotes((prev) => cursor ? [...prev, ...page.data] : page.data);
      setNotesCursor(page.nextCursor);
      setNotesLoaded(true);
    } catch (reason) { toast.error(errorMessage(reason, "Notes could not be loaded.")); }
  }, [patientId, toast]);

  const loadHistory = useCallback(async () => {
    try {
      const data = await api<HistoryEvent[]>(`/api/v1/patients/${patientId}/history`);
      setHistory(data ?? []);
      setHistoryLoaded(true);
    } catch (reason) { toast.error(errorMessage(reason, "Timeline could not be loaded.")); }
  }, [patientId, toast]);

  const loadAppointments = useCallback(async () => {
    try {
      const data = await api<Appointment[]>(`/api/v1/appointments?patient_id=${patientId}&limit=100`);
      setAppointments(data ?? []);
      setAppointmentsLoaded(true);
    } catch (reason) { toast.error(errorMessage(reason, "Appointments could not be loaded.")); }
  }, [patientId, toast]);

  const loadDocuments = useCallback(async () => {
    try {
      const response = await fetch(`/api/v1/patients/${patientId}/documents`, { credentials: "include", cache: "no-store" });
      if (response.ok) {
        const payload = await response.json();
        const items = Array.isArray(payload.data) ? payload.data : payload.data?.items ?? [];
        setDocuments(items);
        setDocumentsError(null);
      } else {
        setDocuments([]);
        setDocumentsError("Private documents are not available for this role.");
      }
      setDocumentsLoaded(true);
    } catch { setDocumentsError("Documents could not be loaded."); setDocumentsLoaded(true); }
  }, [patientId]);

  const loadConsents = useCallback(async () => {
    try {
      const data = await api<Consent[]>(`/api/v1/patients/${patientId}/consents`);
      setConsents(data ?? []);
      setConsentsLoaded(true);
    } catch (reason) { toast.error(errorMessage(reason, "Consents could not be loaded.")); }
  }, [patientId, toast]);

  const loadPrescriptions = useCallback(async () => {
    try {
      const data = await api<Prescription[]>(`/api/v1/patients/${patientId}/prescriptions`);
      setPrescriptions(data ?? []);
      setPrescriptionsLoaded(true);
    } catch (reason) { toast.error(errorMessage(reason, "Prescriptions could not be loaded.")); }
  }, [patientId, toast]);

  const loadInvoices = useCallback(async () => {
    try {
      const page = await apiPage<Invoice>(`/api/v1/invoices?patient_id=${patientId}&limit=100`);
      setInvoices(page.data);
      setInvoicesLoaded(true);
    } catch (reason) { toast.error(errorMessage(reason, "Invoices could not be loaded.")); }
  }, [patientId, toast]);

  useEffect(() => {
    if (activeTab === "notes" && !notesLoaded) void loadNotes();
    if (activeTab === "timeline" && !historyLoaded) void loadHistory();
    if (activeTab === "appointments" && !appointmentsLoaded) void loadAppointments();
    if (activeTab === "documents" && !documentsLoaded) void loadDocuments();
    if (activeTab === "consents" && !consentsLoaded) void loadConsents();
    if (activeTab === "prescriptions" && !prescriptionsLoaded) void loadPrescriptions();
    if (activeTab === "invoices" && !invoicesLoaded) void loadInvoices();
  }, [activeTab, notesLoaded, historyLoaded, appointmentsLoaded, documentsLoaded, consentsLoaded, prescriptionsLoaded, invoicesLoaded, loadNotes, loadHistory, loadAppointments, loadDocuments, loadConsents, loadPrescriptions, loadInvoices]);

  function startEditing() {
    if (!patient) return;
    setEditName(patient.full_name);
    setEditEmail(patient.normalized_email ?? "");
    setEditPhone(patient.normalized_phone ?? "");
    setEditDob(patient.date_of_birth ?? "");
    setEditing(true);
  }

  async function saveDetails(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!patient) return;
    setSaving(true);
    try {
      const body: Record<string, unknown> = { expected_version: patient.version };
      if (editName.trim() !== patient.full_name) body.full_name = editName.trim();
      if (editEmail.trim() !== (patient.normalized_email ?? "")) body.email = editEmail.trim() || null;
      if (editPhone.trim() !== (patient.normalized_phone ?? "")) body.phone = editPhone.trim() || null;
      if (editDob !== (patient.date_of_birth ?? "")) body.date_of_birth = editDob || null;
      if (Object.keys(body).length === 1) { setEditing(false); return; }
      const response = await fetch(`/api/v1/patients/${patientId}`, {
        method: "PATCH", credentials: "include",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken() },
        body: JSON.stringify(body),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload?.error?.message ?? "The patient details could not be saved.");
      setEditing(false);
      toast.success("Patient details updated.");
      await loadCore();
    } catch (reason) { toast.error(errorMessage(reason, "The patient details could not be saved.")); }
    finally { setSaving(false); }
  }

  async function archivePatient() {
    const yes = await confirm({ message: "Archive this patient record? This action can be reversed by an administrator.", danger: true });
    if (!yes) return;
    try {
      const response = await fetch(`/api/v1/patients/${patientId}/archive`, {
        method: "POST", credentials: "include",
        headers: { "X-CSRF-Token": csrfToken() },
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload?.error?.message ?? "The patient could not be archived.");
      toast.success("Patient archived. Returning to the directory…");
      setTimeout(() => { window.location.href = "/patients"; }, 700);
    } catch (reason) { toast.error(errorMessage(reason, "The patient could not be archived.")); }
  }

  async function downloadDocument(item: Document) {
    setDownloading(item.id);
    try {
      const access = await api<{ access_token: string; expires_at: number }>(`/api/v1/documents/${item.id}/signed-access`, { method: "POST", credentials: "include" });
      const response = await fetch(`/api/v1/documents/${item.id}/download`, {
        credentials: "include",
        headers: { "X-Document-Access-Token": access.access_token, "X-Document-Expires": String(access.expires_at) },
      });
      if (!response.ok) throw new Error("The document is not currently available.");
      const blob = await response.blob();
      const link = window.document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = item.original_filename;
      link.click();
      URL.revokeObjectURL(link.href);
    } catch (reason) { toast.error(errorMessage(reason, "The document could not be downloaded.")); }
    finally { setDownloading(null); }
  }

  return (
    <section className="dash-content patient-detail-content" aria-busy={loading}>
      <Link className="back-link" href="/patients">← Patient directory</Link>

      {error && (
        <div className="workspace-alert" role="alert">
          <strong>{error}</strong>
          <button className="ghost-button" type="button" onClick={() => void loadCore()}>Try again <span>→</span></button>
        </div>
      )}

      {loading && (
        <div className="dashboard-empty" role="status">
          <strong>Loading authorized record</strong>
          <span>Checking patient scope and related records…</span>
        </div>
      )}

      {!loading && patient && (
        <>
          <div className="patient-hero">
            <div className="patient-initial patient-initial-large" aria-hidden="true">{patient.full_name.trim().charAt(0).toUpperCase()}</div>
            <div>
              <p className="eyebrow">PATIENT RECORD · {patient.patient_number}</p>
              <h1>{patient.full_name}</h1>
              <p className="patient-status">{statusLabel(patient.status)} · version {patient.version}</p>
            </div>
            <div className="patient-hero-actions">
              <button className="button button-secondary" type="button" onClick={() => void loadCore()}>Refresh <span>↻</span></button>
              {can("patient.update") && !editing && <button className="text-control" type="button" onClick={startEditing}>Edit details</button>}
              {can("patient.update") && <button className="text-control" type="button" onClick={() => setMergeOpen(true)}>Merge</button>}
              {can("patient.archive") && <button className="text-control danger-control" type="button" onClick={() => void archivePatient()}>Archive patient</button>}
            </div>
          </div>

          <div className="patient-tabs" role="tablist" aria-label="Patient sections">
            {tabs.map((tab) => (
              <button
                key={tab.key}
                role="tab"
                className={activeTab === tab.key ? "active" : ""}
                aria-selected={activeTab === tab.key}
                onClick={() => setActiveTab(tab.key)}
                type="button"
              >
                {tab.label}
              </button>
            ))}
          </div>

          <div className="patient-tab-panel" role="tabpanel">
            {activeTab === "overview" && (
              <div className="detail-grid">
                <section className="detail-card">
                  <p className="eyebrow">CONTACT</p>
                  <h2>Reach them</h2>
                  {editing ? (
                    <form className="patient-edit-form" onSubmit={(e) => void saveDetails(e)}>
                      <label>Full name<input required value={editName} onChange={(e) => setEditName(e.target.value)} /></label>
                      <label>Email<input type="email" value={editEmail} onChange={(e) => setEditEmail(e.target.value)} placeholder="Not recorded" /></label>
                      <label>Phone<input value={editPhone} onChange={(e) => setEditPhone(e.target.value)} placeholder="Not recorded" /></label>
                      <label>Date of birth<input type="date" value={editDob} onChange={(e) => setEditDob(e.target.value)} /></label>
                      <div className="form-actions">
                        <button className="button button-primary" type="submit" disabled={saving}>{saving ? "Saving…" : "Save details"}</button>
                        <button className="ghost-button" type="button" onClick={() => setEditing(false)} disabled={saving}>Cancel</button>
                      </div>
                    </form>
                  ) : (
                    <dl>
                      <div><dt>Email</dt><dd>{patient.normalized_email ?? "Not recorded"}</dd></div>
                      <div><dt>Phone</dt><dd>{patient.normalized_phone ?? "Not recorded"}</dd></div>
                      <div><dt>Date of birth</dt><dd>{patient.date_of_birth ?? "Not recorded"}</dd></div>
                    </dl>
                  )}
                  {contacts.length > 0 && (
                    <div className="contact-list">
                      {contacts.map((c) => <p key={c.id}><span>{c.contact_type}</span>{c.value}{c.is_primary ? " · primary" : ""}</p>)}
                    </div>
                  )}
                </section>

                <section className="detail-card">
                  <p className="eyebrow">CARE TEAM</p>
                  <h2>Assigned clinicians</h2>
                  {careTeam.length === 0 ? (
                    <div className="dashboard-empty"><strong>No care-team assignment</strong><span>Only explicitly assigned clinicians can write care-team notes.</span></div>
                  ) : (
                    <div className="care-team-list" role="list">
                      {careTeam.map((m) => (
                        <div className="care-team-member" key={m.doctor_id} role="listitem">
                          <span className="care-team-mark" aria-hidden="true">+</span>
                          <div><strong>{m.public_name}</strong><small>{m.specialty ?? "Clinician"}</small></div>
                        </div>
                      ))}
                    </div>
                  )}
                </section>

                <section className="detail-card">
                  <p className="eyebrow">QUICK STATS</p>
                  <h2>At a glance</h2>
                  <dl>
                    <div><dt>Status</dt><dd>{statusLabel(patient.status)}</dd></div>
                    <div><dt>Record #</dt><dd>{patient.patient_number}</dd></div>
                    <div><dt>Version</dt><dd>{patient.version}</dd></div>
                  </dl>
                </section>
              </div>
            )}

            {activeTab === "timeline" && (
              <section className="detail-card">
                <div className="card-heading">
                  <div><p className="eyebrow">PATIENT HISTORY</p><h2>Event timeline</h2></div>
                  <span className="directory-count">{history.length} events</span>
                </div>
                {!historyLoaded ? (
                  <div className="dashboard-empty" role="status"><strong>Loading timeline…</strong></div>
                ) : history.length === 0 ? (
                  <div className="dashboard-empty"><strong>No events recorded</strong><span>Appointment changes and merges will appear here.</span></div>
                ) : (
                  <div className="timeline-list">
                    {history.map((event) => (
                      <article className="timeline-item" key={event.id}>
                        <div className="timeline-marker" />
                        <div className="timeline-body">
                          <div className="timeline-header">
                            <span className={`timeline-type type-${event.event_type}`}>{statusLabel(event.event_type)}</span>
                            <time dateTime={event.created_at}>{formatDateTime(event.created_at)}</time>
                          </div>
                          {event.from_status && event.to_status && (
                            <p>{statusLabel(event.from_status)} → {statusLabel(event.to_status)}</p>
                          )}
                          {event.reason && <p className="timeline-reason">{event.reason}</p>}
                        </div>
                      </article>
                    ))}
                  </div>
                )}
              </section>
            )}

            {activeTab === "appointments" && (
              <section className="detail-card">
                <div className="card-heading">
                  <div><p className="eyebrow">APPOINTMENT HISTORY</p><h2>Visits</h2></div>
                  <span className="directory-count">{appointments.length} shown</span>
                </div>
                {!appointmentsLoaded ? (
                  <div className="dashboard-empty" role="status"><strong>Loading appointments…</strong></div>
                ) : appointments.length === 0 ? (
                  <div className="dashboard-empty"><strong>No appointments</strong><span>This patient has no appointment records in scope.</span></div>
                ) : (
                  <div className="appointment-list-table">
                    {appointments.map((a) => (
                      <div className="appointment-list-row" key={a.id}>
                        <div>
                          <strong>{a.reference}</strong>
                          <small>{formatDate(a.starts_at)} · {formatTime(a.starts_at)} – {formatTime(a.ends_at)}</small>
                        </div>
                        <span className={`pipeline-status status-${a.status}`}>{statusLabel(a.status)}</span>
                      </div>
                    ))}
                  </div>
                )}
              </section>
            )}

            {activeTab === "notes" && (
              <section className="detail-card">
                <div className="card-heading">
                  <div><p className="eyebrow">AUTHORIZED NOTES</p><h2>Care context</h2></div>
                  <span className="directory-count">{notes.length} shown</span>
                </div>
                {!notesLoaded ? (
                  <div className="dashboard-empty" role="status"><strong>Loading notes…</strong></div>
                ) : notes.length === 0 ? (
                  <div className="dashboard-empty"><strong>No notes available</strong><span>Notes are shown only when your role permits their visibility.</span></div>
                ) : (
                  <>
                    <div className="note-list">
                      {notes.map((note) => (
                        <article className="note-item" key={note.id}>
                          <div>
                            <span>{note.note_type} · {note.visibility.replaceAll("_", " ")}</span>
                            <time dateTime={note.created_at}>{formatDate(note.created_at)}</time>
                          </div>
                          <p>{note.body}</p>
                        </article>
                      ))}
                    </div>
                    {notesCursor && (
                      <button className="button button-secondary" type="button" onClick={() => void loadNotes(notesCursor)}>Load more notes</button>
                    )}
                  </>
                )}
              </section>
            )}

            {activeTab === "documents" && (
              <section className="detail-card">
                <div className="card-heading">
                  <div><p className="eyebrow">PRIVATE DOCUMENTS</p><h2>Authorized files</h2></div>
                  <span className="directory-count">{documents.length} shown</span>
                </div>
                {!documentsLoaded ? (
                  <div className="dashboard-empty" role="status"><strong>Loading documents…</strong></div>
                ) : documentsError ? (
                  <div className="dashboard-empty"><strong>Documents are restricted</strong><span>{documentsError}</span></div>
                ) : documents.length === 0 ? (
                  <div className="dashboard-empty"><strong>No private documents</strong><span>Files become available after authorization and a clean scan.</span></div>
                ) : (
                  <div className="document-list" role="list">
                    {documents.map((item) => (
                      <div className="document-row" key={item.id} role="listitem">
                        <div>
                          <strong>{item.original_filename}</strong>
                          <small>{item.mime_type} · {Math.round(item.size_bytes / 1024)} KB · {item.scan_status.replaceAll("_", " ")}</small>
                        </div>
                        <button className="button button-secondary" type="button" onClick={() => void downloadDocument(item)} disabled={item.scan_status !== "clean" || downloading !== null}>
                          {downloading === item.id ? "Preparing…" : item.scan_status === "clean" ? "Download" : "Unavailable"}
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </section>
            )}

            {activeTab === "consents" && (
              <section className="detail-card">
                <div className="card-heading">
                  <div><p className="eyebrow">CONSENT RECORDS</p><h2>Patient consents</h2></div>
                  <span className="directory-count">{consents.length} shown</span>
                </div>
                {!consentsLoaded ? (
                  <div className="dashboard-empty" role="status"><strong>Loading consents…</strong></div>
                ) : consents.length === 0 ? (
                  <div className="dashboard-empty"><strong>No consent records</strong><span>Consent tracking records will appear here when created.</span></div>
                ) : (
                  <div className="consent-list">
                    {consents.map((c) => (
                      <div className="consent-row" key={c.id}>
                        <div>
                          <strong>{c.consent_type}</strong>
                          <small>Version {c.version} · {formatDate(c.created_at)}</small>
                        </div>
                        <span className={`pipeline-status status-${c.status}`}>{statusLabel(c.status)}</span>
                      </div>
                    ))}
                  </div>
                )}
              </section>
            )}

            {activeTab === "prescriptions" && (
              <section className="detail-card">
                <div className="card-heading">
                  <div><p className="eyebrow">PRESCRIPTIONS</p><h2>Medication records</h2></div>
                  <span className="directory-count">{prescriptions.length} shown</span>
                </div>
                {!prescriptionsLoaded ? (
                  <div className="dashboard-empty" role="status"><strong>Loading prescriptions…</strong></div>
                ) : prescriptions.length === 0 ? (
                  <div className="dashboard-empty"><strong>No prescriptions</strong><span>Prescriptions will appear here when recorded.</span></div>
                ) : (
                  <div className="prescription-list">
                    {prescriptions.map((p) => (
                      <div className="prescription-row" key={p.id}>
                        <div>
                          <strong>{p.medication_name}</strong>
                          <small>{p.dosage} · {p.frequency}{p.duration_days ? ` · ${p.duration_days} days` : ""}</small>
                        </div>
                        <div>
                          <span className={`pipeline-status status-${p.status}`}>{statusLabel(p.status)}</span>
                          <small>{formatDate(p.created_at)}</small>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </section>
            )}

            {activeTab === "invoices" && (
              <section className="detail-card">
                <div className="card-heading">
                  <div><p className="eyebrow">BILLING</p><h2>Invoices &amp; payments</h2></div>
                  <span className="directory-count">{invoices.length} shown</span>
                </div>
                {!invoicesLoaded ? (
                  <div className="dashboard-empty" role="status"><strong>Loading invoices…</strong></div>
                ) : invoices.length === 0 ? (
                  <div className="dashboard-empty"><strong>No invoices</strong><span>Billing records will appear here when created.</span></div>
                ) : (
                  <div className="invoice-list">
                    {invoices.map((inv) => (
                      <div className="invoice-row" key={inv.id}>
                        <div>
                          <strong>{inv.invoice_number}</strong>
                          <small>Issued {formatDate(inv.issued_at)}</small>
                        </div>
                        <div className="invoice-amounts">
                          <span>{money(inv.total_minor, inv.currency)}</span>
                          <small>{inv.paid_minor >= inv.total_minor ? "Paid" : `${money(inv.paid_minor, inv.currency)} paid`}</small>
                        </div>
                        <span className={`pipeline-status status-${inv.status}`}>{statusLabel(inv.status)}</span>
                      </div>
                    ))}
                  </div>
                )}
              </section>
            )}
          </div>

          <p className="privacy-caption detail-privacy">This view is limited by your authenticated clinic and role scope.</p>

          <MergePatientDrawer
            open={mergeOpen}
            onClose={() => setMergeOpen(false)}
            sourcePatientId={patientId}
            sourcePatientName={patient.full_name}
            onMerged={() => { window.location.href = "/patients"; }}
          />
        </>
      )}
    </section>
  );
}
