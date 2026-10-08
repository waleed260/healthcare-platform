"use client";

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import anime from "animejs";
import { api, errorMessage, label, post, writeHeaders } from "../_lib/client";
import { useToast } from "../_lib/toast";
import { useConfirm } from "../_lib/confirm";
import Drawer from "../_lib/drawer";

type Clinic = { id: string; name: string; slug: string; status: string; timezone: string; locale: string; version: number; created_at: string; updated_at: string; subscription_status: string | null; renewal_at: string | null; subscription_ends_at: string | null; plan_name: string | null; plan_code: string | null };
type Metrics = { http: Record<string, unknown>; database_pool: { size: number; checked_out: number; overflow: number }; background_jobs: { queued: number; running: number; failed: number; oldest_queued_at: string | null }; telemetry: { appointments: Record<string, number>; booking: Record<string, number | null>; scan_backlog: number; storage_failures: number; publish_failures: number }; billing: Record<string, number> };
type AuditRow = { id: string; action: string; entity_type: string; outcome: string; request_id: string; created_at: string };
type SupportRow = { id: string; clinic_id: string; requested_by_user_id: string; approved_by_user_id: string; reason: string; permissions: Record<string, boolean>; starts_at: string; expires_at: string; revoked_at: string | null };
type Plan = { id: string; code: string; name: string; active: boolean; created_at: string; limits: Record<string, { limit_value: number; enabled: boolean }> };
type Announcement = { id: string; title: string; body: string; severity: string; starts_at: string; ends_at: string | null; created_at: string };
type Session = { is_platform_admin?: boolean };

type Tab = "clinics" | "metrics" | "support" | "audit" | "plans" | "announcements";

function date(value: string): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}
function shortDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "short" }).format(new Date(value));
}

export default function AdminPage() {
  const [tab, setTab] = useState<Tab>("clinics");
  const [clinics, setClinics] = useState<Clinic[]>([]);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [support, setSupport] = useState<SupportRow[]>([]);
  const [audit, setAudit] = useState<AuditRow[]>([]);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [announcements, setAnnouncements] = useState<Announcement[]>([]);
  const [isAdmin, setIsAdmin] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [clinicDrawer, setClinicDrawer] = useState<Clinic | null>(null);
  const [announcementForm, setAnnouncementForm] = useState(false);
  const [auditFilter, setAuditFilter] = useState("");

  const [annTitle, setAnnTitle] = useState("");
  const [annBody, setAnnBody] = useState("");
  const [annSeverity, setAnnSeverity] = useState("info");

  const toast = useToast();
  const confirm = useConfirm();

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const session = await api<Session>("/api/v1/auth/me");
      if (!session?.is_platform_admin) {
        setError("Platform administrator access is required.");
        setLoading(false);
        return;
      }
      setIsAdmin(true);
      const [clinicData, metricsData, supportData, auditData, planData, announcementData] = await Promise.all([
        api<Clinic[]>("/api/v1/admin/clinics?limit=50").catch(() => [] as Clinic[]),
        api<Metrics>("/api/v1/admin/metrics").catch(() => null),
        api<SupportRow[]>("/api/v1/admin/support-access").catch(() => [] as SupportRow[]),
        api<AuditRow[]>("/api/v1/admin/audit?limit=50").catch(() => [] as AuditRow[]),
        api<Plan[]>("/api/v1/admin/plans?limit=50").catch(() => [] as Plan[]),
        api<Announcement[]>("/api/v1/admin/announcements?limit=50").catch(() => [] as Announcement[]),
      ]);
      setClinics(clinicData ?? []);
      setMetrics(metricsData);
      setSupport(supportData ?? []);
      setAudit(auditData ?? []);
      setPlans(planData ?? []);
      setAnnouncements(announcementData ?? []);
    } catch (reason) {
      setError(errorMessage(reason, "The admin console could not be loaded."));
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  async function clinicLifecycle(clinic: Clinic, action: "suspend" | "reactivate") {
    const ok = await confirm({ title: `${action === "suspend" ? "Suspend" : "Reactivate"} ${clinic.name}`, message: action === "suspend" ? "All active sessions will be revoked and booking tokens invalidated." : "The clinic will be reactivated and users can sign in again.", confirmLabel: label(action), danger: action === "suspend" });
    if (!ok) return;
    setBusy(true);
    try {
      await post(`/api/v1/admin/clinics/${clinic.id}/lifecycle`, { action, expected_version: clinic.version, reason: `Platform admin ${action}` });
      toast.success(`Clinic ${action === "suspend" ? "suspended" : "reactivated"}.`);
      setClinicDrawer(null);
      await load();
    } catch (reason) {
      toast.error(errorMessage(reason, `The clinic could not be ${action}ed.`));
    } finally {
      setBusy(false);
    }
  }

  async function revokeSupport(id: string) {
    const ok = await confirm({ message: "Revoke this support access session immediately?", danger: true, confirmLabel: "Revoke" });
    if (!ok) return;
    setBusy(true);
    try {
      await api(`/api/v1/admin/support-access/${id}/revoke`, { method: "POST", headers: writeHeaders() });
      toast.success("Support access revoked.");
      await load();
    } catch (reason) {
      toast.error(errorMessage(reason, "The support session could not be revoked."));
    } finally {
      setBusy(false);
    }
  }

  async function createAnnouncement(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    try {
      await post("/api/v1/admin/announcements", { title: annTitle.trim(), body: annBody.trim(), severity: annSeverity });
      setAnnTitle("");
      setAnnBody("");
      setAnnouncementForm(false);
      toast.success("Announcement published.");
      await load();
    } catch (reason) {
      toast.error(errorMessage(reason, "The announcement could not be created."));
    } finally {
      setBusy(false);
    }
  }

  const filteredClinics = useMemo(() => {
    if (!search) return clinics;
    const q = search.toLowerCase();
    return clinics.filter((c) => c.name.toLowerCase().includes(q) || c.slug.toLowerCase().includes(q));
  }, [clinics, search]);

  const filteredAudit = useMemo(() => {
    if (!auditFilter) return audit;
    const q = auditFilter.toLowerCase();
    return audit.filter((a) => a.action.toLowerCase().includes(q) || a.entity_type.toLowerCase().includes(q));
  }, [audit, auditFilter]);

  const activeSessions = support.filter((s) => !s.revoked_at && new Date(s.expires_at) > new Date());

  if (!isAdmin && !loading) {
    return <main className="workspace-page">
      <div className="workspace-page-header"><div><p className="eyebrow">PLATFORM</p><h1>Access <em>restricted.</em></h1><p className="workspace-page-intro">You need platform administrator privileges to view this console.</p></div></div>
    </main>;
  }

  const tabs: { key: Tab; label: string; count?: number }[] = [
    { key: "clinics", label: "Clinics", count: clinics.length },
    { key: "metrics", label: "Metrics" },
    { key: "support", label: "Support", count: activeSessions.length },
    { key: "audit", label: "Audit", count: audit.length },
    { key: "plans", label: "Plans", count: plans.length },
    { key: "announcements", label: "Announcements", count: announcements.length },
  ];

  const adminRef = useRef<HTMLElement>(null);
  useEffect(() => {
    if (loading || !adminRef.current) return;
    anime({ targets: adminRef.current.querySelectorAll(".surface-card, .invoice-row, .analytics-card, .inventory-summary > div"), opacity: [0, 1], translateY: [22, 0], duration: 500, delay: anime.stagger(40, { start: 100 }), easing: "easeOutCubic" });
  }, [loading, tab]);

  return <main className="workspace-page admin-page" ref={adminRef}>
    <div className="workspace-page-header">
      <div>
        <p className="eyebrow">PLATFORM ADMIN</p>
        <h1>The control <em>room.</em></h1>
        <p className="workspace-page-intro">Clinics, subscriptions, support access, audit trail, and platform health at a glance.</p>
      </div>
      <div className="header-actions">
        <button className="button button-secondary" onClick={() => void load()} disabled={loading}>Refresh <span>↻</span></button>
      </div>
    </div>

    {error && <div className="workspace-alert" role="alert"><strong>{error}</strong><button className="ghost-button" onClick={() => void load()}>Try again <span>→</span></button></div>}
    {loading && <div className="dashboard-empty" role="status"><strong>Loading platform console</strong><span>Aggregating cross-tenant metrics…</span></div>}

    {isAdmin && !loading && <>
      {/* Metrics hero */}
      {metrics && <div className="report-hero-grid" style={{ marginBottom: 20 }}>
        <div className="report-hero-card report-hero-dark">
          <span className="eyebrow">TENANTS</span>
          <strong>{clinics.length}</strong>
          <p>{clinics.filter((c) => c.status === "active").length} active · {clinics.filter((c) => c.status === "suspended").length} suspended</p>
        </div>
        <div className="report-hero-card">
          <span className="eyebrow">APPOINTMENTS</span>
          <strong>{metrics.telemetry.appointments.total}</strong>
          <p>{metrics.telemetry.appointments.completed} completed · {metrics.telemetry.appointments.cancelled} cancelled</p>
        </div>
        <div className={`report-hero-card ${metrics.background_jobs.failed > 0 ? "report-hero-warm" : ""}`}>
          <span className="eyebrow">BACKGROUND JOBS</span>
          <strong>{metrics.background_jobs.queued + metrics.background_jobs.running}</strong>
          <p>{metrics.background_jobs.queued} queued · {metrics.background_jobs.failed} failed</p>
        </div>
      </div>}

      {/* Tab bar */}
      <div className="pipeline-tabs" role="tablist" style={{ marginBottom: 16 }}>
        {tabs.map((t) => <button key={t.key} role="tab" aria-selected={tab === t.key} className={tab === t.key ? "active" : ""} onClick={() => setTab(t.key)}>
          {t.label}{t.count !== undefined ? ` (${t.count})` : ""}
        </button>)}
      </div>

      {/* === Clinics tab === */}
      {tab === "clinics" && <section className="surface-card">
        <div className="surface-card-heading">
          <div><p className="eyebrow">TENANT LIST</p><h2>Registered clinics</h2></div>
          <input type="search" placeholder="Search clinics…" value={search} onChange={(e) => setSearch(e.target.value)} style={{ maxWidth: 220, padding: "6px 12px", border: "1px solid var(--border-subtle, #e5e5e3)", borderRadius: 6, fontSize: "0.85rem", background: "var(--surface-1, #fff)" }} />
        </div>
        {filteredClinics.length === 0 ? <div className="dashboard-empty"><strong>{search ? "No matching clinics" : "No clinics registered"}</strong><span>Tenants appear here after onboarding.</span></div>
          : <div className="invoice-list">
            {filteredClinics.map((clinic) => <article className="invoice-row" key={clinic.id} style={{ cursor: "pointer" }} onClick={() => setClinicDrawer(clinic)}>
              <div className="invoice-mark">{clinic.name.slice(0, 2).toUpperCase()}</div>
              <div className="invoice-main">
                <h3>{clinic.name}</h3>
                <p>{clinic.slug} · {clinic.timezone}{clinic.plan_name ? ` · ${clinic.plan_name}` : ""}</p>
                <small>Created {shortDate(clinic.created_at)}{clinic.subscription_status ? ` · Subscription: ${label(clinic.subscription_status)}` : " · No subscription"}</small>
              </div>
              <div className="invoice-actions">
                <span className={`pipeline-status ${clinic.status === "active" ? "status-paid" : "status-void"}`}>{clinic.status.toUpperCase()}</span>
              </div>
            </article>)}
          </div>}
      </section>}

      {/* === Metrics tab === */}
      {tab === "metrics" && metrics && <div className="report-grid">
        <section className="surface-card report-card">
          <div className="surface-card-heading"><div><p className="eyebrow">DATABASE</p><h2>Connection pool</h2></div></div>
          <div className="report-health-grid">
            <div><strong>{metrics.database_pool.size}</strong><span>pool size</span></div>
            <div><strong>{metrics.database_pool.checked_out}</strong><span>checked out</span></div>
            <div><strong>{metrics.database_pool.overflow}</strong><span>overflow</span></div>
          </div>
        </section>

        <section className="surface-card report-card">
          <div className="surface-card-heading"><div><p className="eyebrow">BILLING HEALTH</p><h2>Subscription status</h2></div></div>
          <div className="report-health-grid">
            <div><strong>{metrics.billing.active ?? 0}</strong><span>active</span></div>
            <div><strong>{metrics.billing.trialing ?? 0}</strong><span>trialing</span></div>
            <div><strong>{metrics.billing.past_due ?? 0}</strong><span>past due</span></div>
            <div><strong>{metrics.billing.cancelled ?? 0}</strong><span>cancelled</span></div>
          </div>
        </section>

        <section className="surface-card report-card">
          <div className="surface-card-heading"><div><p className="eyebrow">CARE FLOW</p><h2>Appointments</h2></div></div>
          <div className="report-health-grid">
            <div><strong>{metrics.telemetry.appointments.requested}</strong><span>requested</span></div>
            <div><strong>{metrics.telemetry.appointments.confirmed}</strong><span>confirmed</span></div>
            <div><strong>{metrics.telemetry.appointments.completed}</strong><span>completed</span></div>
            <div><strong>{metrics.telemetry.appointments.cancelled}</strong><span>cancelled</span></div>
          </div>
        </section>

        <section className="surface-card report-card">
          <div className="surface-card-heading"><div><p className="eyebrow">OPERATIONS</p><h2>Background health</h2></div></div>
          <div className="report-health-grid">
            <div><strong>{metrics.telemetry.scan_backlog}</strong><span>scan backlog</span></div>
            <div><strong>{metrics.telemetry.storage_failures}</strong><span>storage failures</span></div>
            <div><strong>{metrics.telemetry.publish_failures}</strong><span>publish failures</span></div>
            <div><strong>{metrics.billing.none ?? 0}</strong><span>no subscription</span></div>
          </div>
        </section>
      </div>}

      {/* === Support tab === */}
      {tab === "support" && <section className="surface-card">
        <div className="surface-card-heading">
          <div><p className="eyebrow">SUPPORT ACCESS</p><h2>Timed support sessions</h2></div>
          <span className="muted-mono">{activeSessions.length} ACTIVE</span>
        </div>
        {support.length === 0 ? <div className="dashboard-empty"><strong>No support sessions</strong><span>Support access sessions appear here when created.</span></div>
          : <div className="invoice-list">
            {support.map((item) => {
              const expired = new Date(item.expires_at) <= new Date();
              const revoked = !!item.revoked_at;
              const active = !expired && !revoked;
              return <article className="invoice-row" key={item.id}>
                <div className="invoice-mark">{active ? "●" : "○"}</div>
                <div className="invoice-main">
                  <h3>Clinic {item.clinic_id.slice(0, 8)}…</h3>
                  <p>{item.reason}</p>
                  <small>{date(item.starts_at)} → {date(item.expires_at)}{revoked ? ` · Revoked ${date(item.revoked_at!)}` : ""}</small>
                </div>
                <div className="invoice-actions">
                  <span className={`pipeline-status ${active ? "status-paid" : revoked ? "status-void" : "status-pending"}`}>{revoked ? "REVOKED" : expired ? "EXPIRED" : "ACTIVE"}</span>
                  {active && <button className="text-control" disabled={busy} onClick={() => void revokeSupport(item.id)}>Revoke</button>}
                </div>
              </article>;
            })}
          </div>}
      </section>}

      {/* === Audit tab === */}
      {tab === "audit" && <section className="surface-card">
        <div className="surface-card-heading">
          <div><p className="eyebrow">PLATFORM AUDIT</p><h2>Global event log</h2></div>
          <input type="search" placeholder="Filter by action…" value={auditFilter} onChange={(e) => setAuditFilter(e.target.value)} style={{ maxWidth: 220, padding: "6px 12px", border: "1px solid var(--border-subtle, #e5e5e3)", borderRadius: 6, fontSize: "0.85rem", background: "var(--surface-1, #fff)" }} />
        </div>
        {filteredAudit.length === 0 ? <div className="dashboard-empty"><strong>{auditFilter ? "No matching events" : "No audit events"}</strong><span>Platform actions will be logged here.</span></div>
          : <div className="invoice-list">
            {filteredAudit.map((item) => <article className="invoice-row" key={item.id}>
              <div className="invoice-mark" style={{ fontSize: "0.7rem" }}>⊙</div>
              <div className="invoice-main">
                <h3>{item.action}</h3>
                <p>{item.entity_type} · {item.outcome}</p>
                <small>{date(item.created_at)}</small>
              </div>
              <div className="invoice-actions">
                <span className={`pipeline-status ${item.outcome === "success" ? "status-paid" : "status-void"}`}>{item.outcome.toUpperCase()}</span>
              </div>
            </article>)}
          </div>}
      </section>}

      {/* === Plans tab === */}
      {tab === "plans" && <section className="surface-card">
        <div className="surface-card-heading">
          <div><p className="eyebrow">SUBSCRIPTION PLANS</p><h2>Available plans</h2></div>
          <span className="muted-mono">{plans.length} PLANS</span>
        </div>
        {plans.length === 0 ? <div className="dashboard-empty"><strong>No plans configured</strong><span>Create plans to offer subscription tiers.</span></div>
          : <div className="invoice-list">
            {plans.map((plan) => <article className="invoice-row" key={plan.id}>
              <div className="invoice-mark">{plan.code.slice(0, 2).toUpperCase()}</div>
              <div className="invoice-main">
                <h3>{plan.name}</h3>
                <p>Code: {plan.code} · {Object.keys(plan.limits).length} feature limits</p>
                <small>Created {shortDate(plan.created_at)}</small>
                {Object.keys(plan.limits).length > 0 && <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 6 }}>
                  {Object.entries(plan.limits).map(([code, limit]) => <span key={code} style={{ fontSize: "0.72rem", padding: "2px 6px", borderRadius: 4, background: "var(--surface-2, #f5f5f0)", color: "var(--text-secondary, #666)" }}>{code}: {limit.limit_value}{!limit.enabled ? " (off)" : ""}</span>)}
                </div>}
              </div>
              <div className="invoice-actions">
                <span className={`pipeline-status ${plan.active ? "status-paid" : "status-void"}`}>{plan.active ? "ACTIVE" : "INACTIVE"}</span>
              </div>
            </article>)}
          </div>}
      </section>}

      {/* === Announcements tab === */}
      {tab === "announcements" && <section className="surface-card">
        <div className="surface-card-heading">
          <div><p className="eyebrow">SYSTEM ANNOUNCEMENTS</p><h2>Broadcast messages</h2></div>
          <button className="button button-primary" onClick={() => setAnnouncementForm((v) => !v)}>{announcementForm ? "Cancel" : "New"} <span>{announcementForm ? "✕" : "＋"}</span></button>
        </div>

        {announcementForm && <form style={{ padding: "16px 20px" }} onSubmit={(e) => void createAnnouncement(e)}>
          <div className="form-grid">
            <label>Title<input required value={annTitle} onChange={(e) => setAnnTitle(e.target.value)} placeholder="What should users know?" /></label>
            <label>Severity
              <select value={annSeverity} onChange={(e) => setAnnSeverity(e.target.value)}>
                <option value="info">Info</option>
                <option value="warning">Warning</option>
                <option value="critical">Critical</option>
              </select>
            </label>
            <label>Body<textarea required value={annBody} onChange={(e) => setAnnBody(e.target.value)} rows={3} placeholder="Details about the announcement" /></label>
          </div>
          <div className="form-actions">
            <button className="button button-primary" type="submit" disabled={busy}>{busy ? "Publishing…" : "Publish announcement"} <span>↗</span></button>
          </div>
        </form>}

        {announcements.length === 0 && !announcementForm ? <div className="dashboard-empty"><strong>No announcements</strong><span>System-wide announcements appear here.</span></div>
          : <div className="invoice-list">
            {announcements.map((item) => <article className="invoice-row" key={item.id}>
              <div className="invoice-mark" style={{ fontSize: "0.8rem" }}>{item.severity === "critical" ? "⚠" : item.severity === "warning" ? "△" : "ⓘ"}</div>
              <div className="invoice-main">
                <h3>{item.title}</h3>
                <p>{item.body.length > 120 ? `${item.body.slice(0, 120)}…` : item.body}</p>
                <small>{date(item.starts_at)}{item.ends_at ? ` → ${date(item.ends_at)}` : " · No expiry"}</small>
              </div>
              <div className="invoice-actions">
                <span className={`pipeline-status ${item.severity === "critical" ? "status-lost" : item.severity === "warning" ? "status-pending" : "status-paid"}`}>{item.severity.toUpperCase()}</span>
              </div>
            </article>)}
          </div>}
      </section>}

      {/* Clinic detail drawer */}
      <Drawer open={!!clinicDrawer} onClose={() => setClinicDrawer(null)} title={clinicDrawer?.name ?? ""} subtitle={clinicDrawer?.slug}>
        {clinicDrawer && <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div className="form-grid">
            <label>Status
              <span className={`pipeline-status ${clinicDrawer.status === "active" ? "status-paid" : "status-void"}`} style={{ display: "inline-block", marginLeft: 8 }}>{clinicDrawer.status.toUpperCase()}</span>
            </label>
            <label>Timezone<input readOnly value={clinicDrawer.timezone} /></label>
            <label>Locale<input readOnly value={clinicDrawer.locale} /></label>
            <label>Plan<input readOnly value={clinicDrawer.plan_name ?? "No plan"} /></label>
            <label>Subscription<input readOnly value={clinicDrawer.subscription_status ? label(clinicDrawer.subscription_status) : "None"} /></label>
            {clinicDrawer.renewal_at && <label>Renewal<input readOnly value={date(clinicDrawer.renewal_at)} /></label>}
            <label>Version<input readOnly value={String(clinicDrawer.version)} /></label>
            <label>Created<input readOnly value={date(clinicDrawer.created_at)} /></label>
            <label>Updated<input readOnly value={date(clinicDrawer.updated_at)} /></label>
          </div>
          <div className="form-actions">
            {clinicDrawer.status === "active"
              ? <button className="button button-danger" disabled={busy} onClick={() => void clinicLifecycle(clinicDrawer, "suspend")}>Suspend clinic</button>
              : <button className="button button-primary" disabled={busy} onClick={() => void clinicLifecycle(clinicDrawer, "reactivate")}>Reactivate clinic</button>}
          </div>
        </div>}
      </Drawer>
    </>}
  </main>;
}
