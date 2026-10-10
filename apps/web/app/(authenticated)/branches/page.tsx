"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import anime from "animejs";
import { api } from "../_lib/client";

type Branch = {
  id: string;
  code: string;
  name: string;
  timezone: string;
  address: string | null;
  phone: string | null;
  email: string | null;
  status: string;
  version: number;
};

type Doctor = {
  id: string;
  doctor_id: string;
  public_name: string;
  specialty: string | null;
};

type Service = {
  id: string;
  name: string;
  category: string | null;
  duration_minutes: number | null;
  amount_minor: number | null;
  currency: string;
};

export default function BranchesPage() {
  const [branches, setBranches] = useState<Branch[]>([]);
  const [branchDoctors, setBranchDoctors] = useState<Record<string, Doctor[]>>({});
  const [branchServices, setBranchServices] = useState<Record<string, Service[]>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api<Branch[]>("/api/v1/branches?limit=100");
      setBranches(data ?? []);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not load branches.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function expandBranch(branchId: string) {
    if (expanded === branchId) { setExpanded(null); return; }
    setExpanded(branchId);
    if (!branchDoctors[branchId]) {
      try {
        const [docs, svcs] = await Promise.all([
          api<Doctor[]>(`/api/v1/branches/${branchId}/doctors?limit=50`),
          api<Service[]>(`/api/v1/branches/${branchId}/services?limit=50`),
        ]);
        setBranchDoctors((prev) => ({ ...prev, [branchId]: docs ?? [] }));
        setBranchServices((prev) => ({ ...prev, [branchId]: svcs ?? [] }));
      } catch { /* silent */ }
    }
  }

  const pageRef = useRef<HTMLElement>(null);
  useEffect(() => {
    if (loading || !pageRef.current) return;
    anime({ targets: pageRef.current.querySelectorAll(".branch-card"), opacity: [0, 1], translateY: [24, 0], duration: 500, delay: anime.stagger(60, { start: 100 }), easing: "easeOutCubic" });
  }, [loading]);

  return (
    <section className="dash-content" ref={pageRef} aria-busy={loading}>
      <div className="dash-topline">
        <div>
          <p className="eyebrow">CLINIC NETWORK</p>
          <h1>Your <em>branches.</em></h1>
        </div>
      </div>
      <p className="queue-intro">All clinic branches, their assigned doctors, and available services.</p>

      {error && <div className="workspace-alert" role="alert"><strong>{error}</strong><button className="ghost-button" type="button" onClick={() => void load()}>Try again <span>→</span></button></div>}

      {loading && branches.length === 0 && <div className="dashboard-empty" role="status"><strong>Loading branches…</strong></div>}
      {!loading && branches.length === 0 && <div className="dashboard-empty"><strong>No branches</strong><span>Create branches from the Manage section.</span></div>}

      <div className="doctors-grid">
        {branches.map((b) => {
          const isOpen = expanded === b.id;
          const docs = branchDoctors[b.id] ?? [];
          const svcs = branchServices[b.id] ?? [];
          return (
            <article className="branch-card panel-card" key={b.id}>
              <div className="card-heading" style={{ cursor: "pointer" }} onClick={() => void expandBranch(b.id)}>
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
                    <span className="doctor-avatar" style={{ background: b.status === "active" ? "var(--leaf)" : "var(--muted)" }}>{b.code?.charAt(0)?.toUpperCase() ?? "B"}</span>
                    <div>
                      <h3 style={{ margin: 0, fontSize: 15 }}>{b.name}</h3>
                      <small style={{ color: "var(--muted)", fontSize: 11 }}>{b.code} · {b.timezone}</small>
                    </div>
                  </div>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span className={`pipeline-status status-${b.status === "active" ? "qualified" : "lost"}`} style={{ fontSize: 10 }}>{b.status}</span>
                  <span className={`nav-group-chevron ${isOpen ? "" : "collapsed"}`} style={{ fontSize: 18 }} aria-hidden="true">›</span>
                </div>
              </div>

              {b.address && <p style={{ margin: "8px 0 0", fontSize: 12, color: "var(--muted)" }}>{b.address}</p>}
              {b.phone && <p style={{ margin: "4px 0 0", fontSize: 12, color: "var(--muted)" }}>{b.phone}</p>}

              {isOpen && (
                <div style={{ borderTop: "1px solid var(--line)", marginTop: 12, paddingTop: 12 }}>
                  <p className="eyebrow" style={{ marginBottom: 8 }}>DOCTORS ({docs.length})</p>
                  {docs.length === 0 ? <p style={{ color: "var(--muted)", fontSize: 12 }}>No doctors assigned.</p> : (
                    <div style={{ display: "grid", gap: 6, marginBottom: 16 }}>
                      {docs.map((d) => (
                        <div key={d.id} style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 0" }}>
                          <span className="doctor-avatar" style={{ width: 28, height: 28, fontSize: 11 }}>{(d.public_name ?? "D").charAt(0)}</span>
                          <div>
                            <strong style={{ fontSize: 13 }}>{d.public_name}</strong>
                            {d.specialty && <small style={{ display: "block", color: "var(--muted)", fontSize: 10 }}>{d.specialty}</small>}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  <p className="eyebrow" style={{ marginBottom: 8 }}>SERVICES ({svcs.length})</p>
                  {svcs.length === 0 ? <p style={{ color: "var(--muted)", fontSize: 12 }}>No services configured.</p> : (
                    <div style={{ display: "grid", gap: 4 }}>
                      {svcs.map((s) => (
                        <div key={s.id} style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid var(--line)", fontSize: 12 }}>
                          <div>
                            <strong>{s.name}</strong>
                            {s.category && <small style={{ color: "var(--muted)", marginLeft: 6 }}>{s.category}</small>}
                          </div>
                          <div style={{ textAlign: "right", color: "var(--muted)", fontSize: 11 }}>
                            {s.duration_minutes && <span>{s.duration_minutes} min</span>}
                            {s.amount_minor != null && <span style={{ marginLeft: 8 }}>{(s.amount_minor / 100).toLocaleString()} {s.currency}</span>}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}
