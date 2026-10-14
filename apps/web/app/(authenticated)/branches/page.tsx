"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, writeHeaders, errorMessage } from "../_lib/client";
import { useToast } from "../_lib/toast";

type Branch = {
  id: string;
  code: string;
  name: string;
  timezone: string;
  address: Record<string, string> | null;
  phone: string | null;
  status: string;
  version: number;
};

type Doctor = {
  id: string;
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

type BranchHour = {
  id: string;
  branch_id: string;
  weekday: number;
  interval_index: number;
  opens_at: string | null;
  closes_at: string | null;
  is_closed: boolean;
};

const WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

function formatAddress(address: Record<string, string> | null): string {
  if (!address || Object.keys(address).length === 0) return "";
  const ordered = [address.line1, address.line2, address.city, address.state, address.postal_code, address.country];
  const parts = ordered.filter(Boolean);
  if (parts.length > 0) return parts.join(", ");
  return Object.values(address).filter(Boolean).join(", ");
}

function timeDisplay(value: string | null): string {
  if (!value) return "—";
  return value.slice(0, 5);
}

type HourDraft = { opens: string; closes: string; closed: boolean };

function defaultHourDrafts(hours: BranchHour[]): HourDraft[] {
  const drafts: HourDraft[] = WEEKDAY_NAMES.map((_, i) => ({ opens: "09:00", closes: "17:00", closed: i === 6 }));
  for (const h of hours) {
    if (h.weekday >= 0 && h.weekday < 7 && h.interval_index === 0) {
      drafts[h.weekday] = {
        opens: h.opens_at ? h.opens_at.slice(0, 5) : "09:00",
        closes: h.closes_at ? h.closes_at.slice(0, 5) : "17:00",
        closed: h.is_closed,
      };
    }
  }
  return drafts;
}

export default function BranchesPage() {
  const toast = useToast();
  const [branches, setBranches] = useState<Branch[]>([]);
  const [branchDoctors, setBranchDoctors] = useState<Record<string, Doctor[]>>({});
  const [branchServices, setBranchServices] = useState<Record<string, Service[]>>({});
  const [branchHours, setBranchHours] = useState<Record<string, BranchHour[]>>({});
  const [hourDrafts, setHourDrafts] = useState<Record<string, HourDraft[]>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [savingDay, setSavingDay] = useState<string | null>(null);

  const canEditHours = permissions.includes("schedule.manage");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [session, data] = await Promise.all([
        api<{ permissions?: string[] }>("/api/v1/auth/me"),
        api<Branch[]>("/api/v1/branches?limit=100"),
      ]);
      setPermissions(session?.permissions ?? []);
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
        const [docs, svcs, hrs] = await Promise.all([
          api<Doctor[]>(`/api/v1/branches/${branchId}/doctors?limit=50`),
          api<Service[]>(`/api/v1/branches/${branchId}/services?limit=50`),
          api<BranchHour[]>(`/api/v1/branches/${branchId}/hours`),
        ]);
        setBranchDoctors((prev) => ({ ...prev, [branchId]: docs ?? [] }));
        setBranchServices((prev) => ({ ...prev, [branchId]: svcs ?? [] }));
        const hoursData = hrs ?? [];
        setBranchHours((prev) => ({ ...prev, [branchId]: hoursData }));
        setHourDrafts((prev) => ({ ...prev, [branchId]: defaultHourDrafts(hoursData) }));
      } catch { /* silent */ }
    }
  }

  function updateDraft(branchId: string, weekday: number, field: keyof HourDraft, value: string | boolean) {
    setHourDrafts((prev) => {
      const drafts = [...(prev[branchId] ?? defaultHourDrafts([]))];
      drafts[weekday] = { ...drafts[weekday], [field]: value };
      return { ...prev, [branchId]: drafts };
    });
  }

  async function saveDay(branchId: string, weekday: number) {
    const draft = hourDrafts[branchId]?.[weekday];
    if (!draft) return;
    const key = `${branchId}-${weekday}`;
    setSavingDay(key);
    try {
      await api(`/api/v1/branches/${branchId}/hours/${weekday}`, {
        method: "PUT",
        headers: writeHeaders(),
        body: JSON.stringify({
          weekday,
          interval_index: 0,
          opens_at: draft.closed ? null : `${draft.opens}:00`,
          closes_at: draft.closed ? null : `${draft.closes}:00`,
          is_closed: draft.closed,
        }),
      });
      toast.success(`${WEEKDAY_NAMES[weekday]} hours saved.`);
      const hrs = await api<BranchHour[]>(`/api/v1/branches/${branchId}/hours`);
      setBranchHours((prev) => ({ ...prev, [branchId]: hrs ?? [] }));
    } catch (reason) {
      toast.error(errorMessage(reason, "Could not save hours."));
    } finally {
      setSavingDay(null);
    }
  }

  async function saveAllDays(branchId: string) {
    const drafts = hourDrafts[branchId];
    if (!drafts) return;
    setSavingDay(`${branchId}-all`);
    try {
      for (let weekday = 0; weekday < 7; weekday++) {
        const draft = drafts[weekday];
        await api(`/api/v1/branches/${branchId}/hours/${weekday}`, {
          method: "PUT",
          headers: writeHeaders(),
          body: JSON.stringify({
            weekday,
            interval_index: 0,
            opens_at: draft.closed ? null : `${draft.opens}:00`,
            closes_at: draft.closed ? null : `${draft.closes}:00`,
            is_closed: draft.closed,
          }),
        });
      }
      toast.success("All hours saved.");
      const hrs = await api<BranchHour[]>(`/api/v1/branches/${branchId}/hours`);
      setBranchHours((prev) => ({ ...prev, [branchId]: hrs ?? [] }));
    } catch (reason) {
      toast.error(errorMessage(reason, "Could not save hours."));
    } finally {
      setSavingDay(null);
    }
  }
  return (
    <main className="dash-content" aria-busy={loading}>
      <div className="dash-topline">
        <div>
          <p className="eyebrow">CLINIC NETWORK</p>
          <h1>Your <em>branches.</em></h1>
        </div>
        <button className="button button-secondary" type="button" onClick={() => void load()} disabled={loading}>Refresh <span>↻</span></button>
      </div>
      <p className="queue-intro">All clinic branches, their assigned doctors, services, and opening hours.</p>

      {error && <div className="workspace-alert" role="alert"><strong>{error}</strong><button className="ghost-button" type="button" onClick={() => void load()}>Try again <span>→</span></button></div>}

      {loading && branches.length === 0 && <div className="dashboard-empty" role="status"><strong>Loading branches…</strong></div>}
      {!loading && branches.length === 0 && <div className="dashboard-empty"><strong>No branches</strong><span>Create branches from the Manage section.</span></div>}

      <div className="doctors-grid">
        {branches.map((b) => {
          const isOpen = expanded === b.id;
          const docs = branchDoctors[b.id] ?? [];
          const svcs = branchServices[b.id] ?? [];
          const hrs = branchHours[b.id] ?? [];
          const drafts = hourDrafts[b.id] ?? defaultHourDrafts([]);
          const addr = formatAddress(b.address);
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

              {addr && <p style={{ margin: "8px 0 0", fontSize: 12, color: "var(--muted)" }}>{addr}</p>}
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
                    <div style={{ display: "grid", gap: 4, marginBottom: 16 }}>
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

                  <p className="eyebrow" style={{ marginBottom: 8 }}>OPENING HOURS</p>
                  {hrs.length === 0 && !canEditHours && <p style={{ color: "var(--muted)", fontSize: 12 }}>No hours configured.</p>}
                  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    {drafts.map((draft, weekday) => (
                      <div key={weekday} style={{ display: "grid", gridTemplateColumns: canEditHours ? "85px 70px 1fr 1fr auto" : "85px 1fr", gap: 8, alignItems: "center", fontSize: "0.82rem" }}>
                        <span style={{ fontWeight: 500 }}>{WEEKDAY_NAMES[weekday]}</span>
                        {canEditHours ? <>
                          <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: "0.78rem", cursor: "pointer" }}>
                            <input type="checkbox" checked={draft.closed} onChange={(e) => updateDraft(b.id, weekday, "closed", e.target.checked)} /> Closed
                          </label>
                          {draft.closed
                            ? <span style={{ gridColumn: "span 2", color: "var(--muted)", fontSize: "0.78rem" }}>—</span>
                            : <>
                              <input type="time" value={draft.opens} onChange={(e) => updateDraft(b.id, weekday, "opens", e.target.value)} style={{ fontSize: "0.8rem", padding: "2px 4px", border: "1px solid var(--line)", borderRadius: 4 }} />
                              <input type="time" value={draft.closes} onChange={(e) => updateDraft(b.id, weekday, "closes", e.target.value)} style={{ fontSize: "0.8rem", padding: "2px 4px", border: "1px solid var(--line)", borderRadius: 4 }} />
                            </>}
                          <button className="ghost-button" type="button" style={{ fontSize: "0.75rem", padding: "2px 8px" }} disabled={savingDay !== null} onClick={() => void saveDay(b.id, weekday)}>{savingDay === `${b.id}-${weekday}` ? "…" : "Save"}</button>
                        </> : <>
                          <span style={{ color: draft.closed ? "var(--muted)" : "inherit", fontSize: "0.8rem" }}>
                            {draft.closed ? "Closed" : `${timeDisplay(draft.opens)} – ${timeDisplay(draft.closes)}`}
                          </span>
                        </>}
                      </div>
                    ))}
                  </div>
                  {canEditHours && (
                    <button className="button button-secondary" type="button" style={{ marginTop: 10, fontSize: "0.8rem" }} disabled={savingDay !== null} onClick={() => void saveAllDays(b.id)}>
                      {savingDay === `${b.id}-all` ? "Saving all…" : "Save all hours"} <span>↗</span>
                    </button>
                  )}
                </div>
              )}
            </article>
          );
        })}
      </div>
    </main>
  );
}
