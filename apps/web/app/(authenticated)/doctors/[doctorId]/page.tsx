"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import anime from "animejs";
import { api, errorMessage, writeHeaders } from "../../_lib/client";
import { useToast } from "../../_lib/toast";

type Service = { id: string; name: string; category: string | null; duration_minutes: number; amount_minor: number | null; currency: string | null; status: string };
type Branch = { id: string; name: string; code: string; status: string };
type AvailabilityRule = { id: string; branch_id: string; branch_name: string; weekday: number; starts_at: string; ends_at: string; slot_cadence_minutes: number; effective_from: string; effective_to: string | null };
type Doctor = {
  id: string; public_name: string; specialty: string | null; registration: string | null;
  license_number: string | null; verification_status: string; bio: string | null;
  phone: string | null; email: string | null; consultation_duration_minutes: number;
  booking_status: string; room_id: string | null; notes: string | null;
  status: string; version: number; created_at: string; updated_at: string;
  total_appointments: number; upcoming_appointments: number; total_patients: number;
  services: Service[]; branches: Branch[]; availability: AvailabilityRule[];
};

const weekdays = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const fmtTime = (v: string) => v.slice(0, 5);
const fmtDate = (v: string) => new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(v));
const bookingLabel: Record<string, string> = { accepting: "Accepting bookings", paused: "Paused", not_accepting: "Not accepting" };
const bookingColor: Record<string, string> = { accepting: "var(--leaf)", paused: "#e0a458", not_accepting: "var(--coral)" };

export default function DoctorDetailPage() {
  const { doctorId } = useParams<{ doctorId: string }>();
  const toast = useToast();

  const [doctor, setDoctor] = useState<Doctor | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<"overview" | "services" | "branches" | "schedule">("overview");

  const [editName, setEditName] = useState("");
  const [editSpecialty, setEditSpecialty] = useState("");
  const [editRegistration, setEditRegistration] = useState("");
  const [editLicense, setEditLicense] = useState("");
  const [editBio, setEditBio] = useState("");
  const [editPhone, setEditPhone] = useState("");
  const [editEmail, setEditEmail] = useState("");
  const [editDuration, setEditDuration] = useState(30);
  const [editBookingStatus, setEditBookingStatus] = useState("accepting");
  const [editNotes, setEditNotes] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const d = await api<Doctor>(`/api/v1/doctors/${doctorId}`);
      if (!d) throw new Error("Not found");
      setDoctor(d);
    } catch (reason) {
      setError(errorMessage(reason, "Doctor could not be loaded."));
    } finally {
      setLoading(false);
    }
  }, [doctorId]);

  useEffect(() => { void load(); }, [load]);

  function startEdit() {
    if (!doctor) return;
    setEditName(doctor.public_name);
    setEditSpecialty(doctor.specialty ?? "");
    setEditRegistration(doctor.registration ?? "");
    setEditLicense(doctor.license_number ?? "");
    setEditBio(doctor.bio ?? "");
    setEditPhone(doctor.phone ?? "");
    setEditEmail(doctor.email ?? "");
    setEditDuration(doctor.consultation_duration_minutes);
    setEditBookingStatus(doctor.booking_status);
    setEditNotes(doctor.notes ?? "");
    setEditing(true);
  }

  async function saveEdit(e: FormEvent) {
    e.preventDefault();
    if (!doctor) return;
    setBusy(true);
    try {
      const body: Record<string, unknown> = { expected_version: doctor.version };
      if (editName.trim() !== doctor.public_name) body.public_name = editName.trim();
      if (editSpecialty !== (doctor.specialty ?? "")) body.specialty = editSpecialty || null;
      if (editRegistration !== (doctor.registration ?? "")) body.registration = editRegistration || null;
      if (editLicense !== (doctor.license_number ?? "")) body.license_number = editLicense || null;
      if (editBio !== (doctor.bio ?? "")) body.bio = editBio || null;
      if (editPhone !== (doctor.phone ?? "")) body.phone = editPhone || null;
      if (editEmail !== (doctor.email ?? "")) body.email = editEmail || null;
      if (editDuration !== doctor.consultation_duration_minutes) body.consultation_duration_minutes = editDuration;
      if (editBookingStatus !== doctor.booking_status) body.booking_status = editBookingStatus;
      if (editNotes !== (doctor.notes ?? "")) body.notes = editNotes || null;
      const keys = Object.keys(body).filter((k) => k !== "expected_version");
      if (keys.length === 0) { setEditing(false); return; }
      await api(`/api/v1/doctors/${doctorId}`, { method: "PATCH", headers: writeHeaders(), body: JSON.stringify(body) });
      toast.success("Doctor profile updated.");
      setEditing(false);
      await load();
    } catch (reason) {
      toast.error(errorMessage(reason, "Could not update doctor."));
    } finally {
      setBusy(false);
    }
  }

  const pageRef = useRef<HTMLElement>(null);
  useEffect(() => {
    if (loading || !pageRef.current) return;
    anime({ targets: pageRef.current.querySelectorAll(".doctor-detail-card"), opacity: [0, 1], translateY: [20, 0], duration: 450, delay: anime.stagger(50, { start: 80 }), easing: "easeOutCubic" });
  }, [loading, tab]);

  if (loading) return <section className="dash-content"><div className="dashboard-empty" role="status"><strong>Loading doctor profile…</strong></div></section>;
  if (error || !doctor) return <section className="dash-content"><div className="workspace-alert" role="alert"><strong>{error ?? "Doctor not found."}</strong></div><Link className="button button-secondary" href="/doctors">Back to doctors</Link></section>;

  return (
    <section className="dash-content" ref={pageRef}>
      <div className="dash-topline">
        <div>
          <p className="eyebrow"><Link href="/doctors" style={{ color: "var(--muted)" }}>DOCTORS</Link> · PROFILE</p>
          <h1>{doctor.public_name}</h1>
          {doctor.specialty && <p style={{ color: "var(--muted)", marginTop: 4, fontSize: 13 }}>{doctor.specialty}</p>}
        </div>
        <div className="header-actions">
          <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, padding: "4px 12px", borderRadius: 20, background: "var(--line)" }}>
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: bookingColor[doctor.booking_status] }} />
            {bookingLabel[doctor.booking_status] ?? doctor.booking_status}
          </span>
          <span className={`pipeline-status status-${doctor.status}`} style={{ fontSize: 11 }}>{doctor.status}</span>
        </div>
      </div>

      <div className="billing-summary">
        <div><span className="eyebrow">TOTAL PATIENTS</span><strong>{doctor.total_patients}</strong></div>
        <div><span className="eyebrow">UPCOMING</span><strong>{doctor.upcoming_appointments}</strong></div>
        <div><span className="eyebrow">ALL APPTS</span><strong>{doctor.total_appointments}</strong></div>
        <div><span className="eyebrow">DURATION</span><strong>{doctor.consultation_duration_minutes}m</strong></div>
      </div>

      <div className="pipeline-toolbar">
        <div className="pipeline-tabs" role="tablist">
          {(["overview", "services", "branches", "schedule"] as const).map((t) => (
            <button key={t} className={tab === t ? "active" : ""} onClick={() => setTab(t)}>{t.charAt(0).toUpperCase() + t.slice(1)}</button>
          ))}
        </div>
      </div>

      {tab === "overview" && (
        <div className="doctor-detail-card surface-card">
          <div className="surface-card-heading">
            <div><p className="eyebrow">PROFILE</p><h2>Doctor information</h2></div>
            {!editing && <button className="button button-secondary" type="button" onClick={startEdit}>Edit profile</button>}
          </div>

          {editing ? (
            <form onSubmit={(e) => void saveEdit(e)}>
              <div className="form-grid">
                <label>Full name *<input required value={editName} onChange={(e) => setEditName(e.target.value)} /></label>
                <label>Specialty<input value={editSpecialty} onChange={(e) => setEditSpecialty(e.target.value)} placeholder="e.g. Dermatology" /></label>
                <label>Registration / PMC #<input value={editRegistration} onChange={(e) => setEditRegistration(e.target.value)} /></label>
                <label>License number<input value={editLicense} onChange={(e) => setEditLicense(e.target.value)} /></label>
                <label>Phone<input value={editPhone} onChange={(e) => setEditPhone(e.target.value)} type="tel" /></label>
                <label>Email<input value={editEmail} onChange={(e) => setEditEmail(e.target.value)} type="email" /></label>
                <label>Consultation duration (min)<input type="number" min={1} max={1440} value={editDuration} onChange={(e) => setEditDuration(Number(e.target.value))} /></label>
                <label>Booking status
                  <select value={editBookingStatus} onChange={(e) => setEditBookingStatus(e.target.value)}>
                    <option value="accepting">Accepting bookings</option>
                    <option value="paused">Paused</option>
                    <option value="not_accepting">Not accepting</option>
                  </select>
                </label>
                <label style={{ gridColumn: "1 / -1" }}>Bio<textarea value={editBio} onChange={(e) => setEditBio(e.target.value)} rows={3} style={{ width: "100%", resize: "vertical" }} /></label>
                <label style={{ gridColumn: "1 / -1" }}>Internal notes<textarea value={editNotes} onChange={(e) => setEditNotes(e.target.value)} rows={2} style={{ width: "100%", resize: "vertical" }} /></label>
              </div>
              <div className="form-actions">
                <button className="button button-secondary" type="button" onClick={() => setEditing(false)}>Cancel</button>
                <button className="button button-primary" type="submit" disabled={busy}>{busy ? "Saving…" : "Save changes"}</button>
              </div>
            </form>
          ) : (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: "16px 24px", padding: "16px 0" }}>
              <InfoField label="Registration" value={doctor.registration} />
              <InfoField label="License" value={doctor.license_number} />
              <InfoField label="Phone" value={doctor.phone} />
              <InfoField label="Email" value={doctor.email} />
              <InfoField label="Duration" value={`${doctor.consultation_duration_minutes} minutes`} />
              <InfoField label="Booking" value={bookingLabel[doctor.booking_status]} />
              <InfoField label="Verification" value={doctor.verification_status} />
              <InfoField label="Joined" value={fmtDate(doctor.created_at)} />
              {doctor.bio && <div style={{ gridColumn: "1 / -1" }}><span className="eyebrow" style={{ fontSize: 10 }}>BIO</span><p style={{ margin: "4px 0 0", fontSize: 13, color: "var(--fg)" }}>{doctor.bio}</p></div>}
              {doctor.notes && <div style={{ gridColumn: "1 / -1" }}><span className="eyebrow" style={{ fontSize: 10 }}>INTERNAL NOTES</span><p style={{ margin: "4px 0 0", fontSize: 13, color: "var(--muted)", fontStyle: "italic" }}>{doctor.notes}</p></div>}
            </div>
          )}
        </div>
      )}

      {tab === "services" && (
        <div className="doctor-detail-card surface-card">
          <div className="surface-card-heading">
            <div><p className="eyebrow">ASSIGNED</p><h2>Services ({doctor.services.length})</h2></div>
          </div>
          {doctor.services.length === 0 ? (
            <div className="dashboard-empty"><strong>No services assigned</strong><span>Assign services from the Manage section.</span></div>
          ) : (
            <div>
              {doctor.services.map((svc) => (
                <div key={svc.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 0", borderBottom: "1px solid var(--line)" }}>
                  <div>
                    <strong style={{ fontSize: 13 }}>{svc.name}</strong>
                    {svc.category && <span style={{ fontSize: 11, color: "var(--muted)", marginLeft: 8 }}>{svc.category}</span>}
                  </div>
                  <div style={{ display: "flex", gap: 12, alignItems: "center", fontSize: 12, color: "var(--muted)" }}>
                    <span>{svc.duration_minutes}min</span>
                    {svc.amount_minor != null && svc.currency && <span>{svc.currency} {(svc.amount_minor / 100).toFixed(2)}</span>}
                    <span className={`pipeline-status status-${svc.status}`} style={{ fontSize: 10 }}>{svc.status}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {tab === "branches" && (
        <div className="doctor-detail-card surface-card">
          <div className="surface-card-heading">
            <div><p className="eyebrow">ASSIGNED</p><h2>Branches ({doctor.branches.length})</h2></div>
          </div>
          {doctor.branches.length === 0 ? (
            <div className="dashboard-empty"><strong>No branches assigned</strong><span>Assign this doctor to branches from the Manage section.</span></div>
          ) : (
            <div>
              {doctor.branches.map((br) => (
                <div key={br.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 0", borderBottom: "1px solid var(--line)" }}>
                  <div>
                    <strong style={{ fontSize: 13 }}>{br.name}</strong>
                    <span style={{ fontSize: 11, color: "var(--muted)", marginLeft: 8 }}>({br.code})</span>
                  </div>
                  <span className={`pipeline-status status-${br.status}`} style={{ fontSize: 10 }}>{br.status}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {tab === "schedule" && (
        <div className="doctor-detail-card surface-card">
          <div className="surface-card-heading">
            <div><p className="eyebrow">WORKING HOURS</p><h2>Availability ({doctor.availability.length} rules)</h2></div>
          </div>
          {doctor.availability.length === 0 ? (
            <div className="dashboard-empty"><strong>No availability rules</strong><span>Set up availability from the Schedule management section.</span></div>
          ) : (
            <div>
              {weekdays.map((day, idx) => {
                const rules = doctor.availability.filter((r) => r.weekday === idx);
                if (rules.length === 0) return null;
                return (
                  <div key={day} style={{ padding: "12px 0", borderBottom: "1px solid var(--line)" }}>
                    <strong style={{ fontSize: 13, minWidth: 90, display: "inline-block" }}>{day}</strong>
                    <div style={{ display: "inline-flex", flexDirection: "column", gap: 4 }}>
                      {rules.map((r) => (
                        <span key={r.id} style={{ fontSize: 12, color: "var(--fg)" }}>
                          {fmtTime(r.starts_at)} – {fmtTime(r.ends_at)}
                          <span style={{ color: "var(--muted)", marginLeft: 8 }}>{r.branch_name}</span>
                          <span style={{ color: "var(--muted)", marginLeft: 8 }}>({r.slot_cadence_minutes}min slots)</span>
                        </span>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function InfoField({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div>
      <span className="eyebrow" style={{ fontSize: 10 }}>{label.toUpperCase()}</span>
      <p style={{ margin: "2px 0 0", fontSize: 13, color: value ? "var(--fg)" : "var(--muted)" }}>{value || "—"}</p>
    </div>
  );
}
