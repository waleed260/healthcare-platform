"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import anime from "animejs";
import { api } from "../_lib/client";

type Doctor = {
  id: string;
  public_name: string;
  specialty: string | null;
  status: string;
  consultation_duration_minutes: number | null;
};
type Appointment = {
  id: string;
  reference: string;
  patient_name: string | null;
  starts_at: string;
  ends_at: string;
  status: string;
};

const time = (v: string) =>
  new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(new Date(v));
const statusClass = (s: string) => `pipeline-status status-${s.replaceAll("_", "-")}`;

export default function DoctorsPage() {
  const [doctors, setDoctors] = useState<Doctor[]>([]);
  const [appointments, setAppointments] = useState<Record<string, Appointment[]>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedDoctor, setExpandedDoctor] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const docs = await api<Doctor[]>("/api/v1/doctors?limit=100");
      setDoctors(docs ?? []);
      if (docs && docs.length > 0) {
        const apptMap: Record<string, Appointment[]> = {};
        const results = await Promise.all(
          docs.map((d) => api<Appointment[]>(`/api/v1/appointments?doctor_id=${d.id}&limit=20`))
        );
        docs.forEach((d, i) => {
          apptMap[d.id] = results[i] ?? [];
        });
        setAppointments(apptMap);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not load doctors.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const pageRef = useRef<HTMLElement>(null);
  useEffect(() => {
    if (loading || !pageRef.current) return;
    anime({
      targets: pageRef.current.querySelectorAll(".doctor-card"),
      opacity: [0, 1],
      translateY: [24, 0],
      duration: 500,
      delay: anime.stagger(60, { start: 100 }),
      easing: "easeOutCubic",
    });
  }, [loading]);

  const activeDoctors = doctors.filter((d) => d.status === "active");
  const inactiveDoctors = doctors.filter((d) => d.status !== "active");

  return (
    <section className="dash-content" ref={pageRef} aria-busy={loading}>
      <div className="dash-topline">
        <div>
          <p className="eyebrow">CLINICAL TEAM</p>
          <h1>
            Your <em>doctors.</em>
          </h1>
        </div>
        <Link className="button button-primary" href="/manage">
          Manage team <span>→</span>
        </Link>
      </div>
      <p className="queue-intro">
        Each doctor&apos;s upcoming appointments and assigned patients at a glance.
      </p>
      {error && (
        <div className="workspace-alert" role="alert">
          <strong>{error}</strong>
          <button className="ghost-button" type="button" onClick={() => void load()}>
            Try again <span>→</span>
          </button>
        </div>
      )}

      {loading && doctors.length === 0 && (
        <div className="dashboard-empty" role="status">
          <strong>Loading doctors…</strong>
        </div>
      )}
      {!loading && doctors.length === 0 && (
        <div className="dashboard-empty">
          <strong>No doctors yet</strong>
          <span>Add doctors from the Manage section to see them here.</span>
        </div>
      )}

      {activeDoctors.length > 0 && (
        <div className="doctors-grid">
          {activeDoctors.map((doc) => {
            const docAppts = appointments[doc.id] ?? [];
            const todayAppts = docAppts.filter((a) => {
              const d = new Date(a.starts_at);
              const now = new Date();
              return (
                d.getFullYear() === now.getFullYear() &&
                d.getMonth() === now.getMonth() &&
                d.getDate() === now.getDate()
              );
            });
            const upcomingAppts = docAppts.filter(
              (a) => new Date(a.starts_at) >= new Date() && !["cancelled", "completed", "no_show"].includes(a.status)
            );
            const isExpanded = expandedDoctor === doc.id;

            return (
              <article className="doctor-card panel-card" key={doc.id}>
                <div className="card-heading" style={{ cursor: "pointer" }} onClick={() => setExpandedDoctor(isExpanded ? null : doc.id)}>
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                      <span className="doctor-avatar">{doc.public_name.charAt(0).toUpperCase()}</span>
                      <div>
                        <h3 style={{ margin: 0, fontSize: 15 }}>{doc.public_name}</h3>
                        {doc.specialty && <small style={{ color: "var(--muted)", fontSize: 11 }}>{doc.specialty}</small>}
                      </div>
                    </div>
                  </div>
                  <span className={`nav-group-chevron ${isExpanded ? "" : "collapsed"}`} style={{ fontSize: 18 }} aria-hidden="true">›</span>
                </div>

                <div className="doctor-stats" style={{ display: "flex", gap: 16, padding: "12px 0", borderTop: "1px solid var(--line)" }}>
                  <div style={{ textAlign: "center", flex: 1 }}>
                    <strong style={{ fontSize: 20 }}>{todayAppts.length}</strong>
                    <small style={{ display: "block", color: "var(--muted)", fontSize: 10 }}>Today</small>
                  </div>
                  <div style={{ textAlign: "center", flex: 1 }}>
                    <strong style={{ fontSize: 20 }}>{upcomingAppts.length}</strong>
                    <small style={{ display: "block", color: "var(--muted)", fontSize: 10 }}>Upcoming</small>
                  </div>
                  <div style={{ textAlign: "center", flex: 1 }}>
                    <strong style={{ fontSize: 20 }}>{doc.consultation_duration_minutes ?? "—"}</strong>
                    <small style={{ display: "block", color: "var(--muted)", fontSize: 10 }}>Min/appt</small>
                  </div>
                </div>

                {isExpanded && (
                  <div style={{ borderTop: "1px solid var(--line)", paddingTop: 12 }}>
                    <p className="eyebrow" style={{ marginBottom: 8 }}>TODAY&apos;S SCHEDULE</p>
                    {todayAppts.length === 0 ? (
                      <p style={{ color: "var(--muted)", fontSize: 12 }}>No appointments today.</p>
                    ) : (
                      <div className="dash-table" style={{ fontSize: 12 }}>
                        {todayAppts.map((a) => (
                          <div className="dash-table-row" key={a.id} style={{ padding: "6px 0" }}>
                            <time dateTime={a.starts_at} style={{ minWidth: 60 }}>{time(a.starts_at)}</time>
                            <span style={{ flex: 1 }}>{a.patient_name ?? a.reference}</span>
                            <span className={statusClass(a.status)} style={{ fontSize: 10 }}>{a.status.replaceAll("_", " ")}</span>
                          </div>
                        ))}
                      </div>
                    )}

                    {upcomingAppts.length > 0 && upcomingAppts.some((a) => {
                      const d = new Date(a.starts_at);
                      const now = new Date();
                      return d.getDate() !== now.getDate() || d.getMonth() !== now.getMonth();
                    }) && <>
                      <p className="eyebrow" style={{ marginTop: 12, marginBottom: 8 }}>UPCOMING</p>
                      <div className="dash-table" style={{ fontSize: 12 }}>
                        {upcomingAppts.filter((a) => {
                          const d = new Date(a.starts_at);
                          const now = new Date();
                          return d.getDate() !== now.getDate() || d.getMonth() !== now.getMonth();
                        }).slice(0, 5).map((a) => (
                          <div className="dash-table-row" key={a.id} style={{ padding: "6px 0" }}>
                            <time dateTime={a.starts_at} style={{ minWidth: 80 }}>
                              {new Date(a.starts_at).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })}
                            </time>
                            <span style={{ flex: 1 }}>{a.patient_name ?? a.reference}</span>
                            <span className={statusClass(a.status)} style={{ fontSize: 10 }}>{a.status.replaceAll("_", " ")}</span>
                          </div>
                        ))}
                      </div>
                    </>}
                  </div>
                )}
              </article>
            );
          })}
        </div>
      )}

      {inactiveDoctors.length > 0 && (
        <>
          <p className="eyebrow" style={{ marginTop: 32, marginBottom: 12 }}>INACTIVE</p>
          <div className="doctors-grid">
            {inactiveDoctors.map((doc) => (
              <article className="doctor-card panel-card" key={doc.id} style={{ opacity: 0.6 }}>
                <div className="card-heading">
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span className="doctor-avatar" style={{ background: "var(--muted)" }}>{doc.public_name.charAt(0).toUpperCase()}</span>
                    <div>
                      <h3 style={{ margin: 0, fontSize: 15 }}>{doc.public_name}</h3>
                      {doc.specialty && <small style={{ color: "var(--muted)", fontSize: 11 }}>{doc.specialty}</small>}
                    </div>
                  </div>
                  <span className={statusClass(doc.status)} style={{ fontSize: 10 }}>{doc.status}</span>
                </div>
              </article>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
