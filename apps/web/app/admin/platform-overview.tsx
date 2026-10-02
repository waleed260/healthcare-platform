"use client";

import { useCallback, useEffect, useState } from "react";
import { api, errorMessage, label, money, post } from "../(authenticated)/_lib/client";

type Overview = {
  clinics: { by_status: Record<string, number>; total: number; onboarded_30d: number };
  subscriptions: { active: number; trialing: number; past_due: number; cancelled: number; mrr_minor: number; overdue_minor: number; renewals_30d: number; trials_ending_14d: number };
  plans: { code: string; clinics: number }[];
  modules: { code: string; clinics: number }[];
  open_upgrade_requests: number;
  client_health: { checked: number; at_risk: { clinic_id: string; name: string; last_login_at: string | null; active_users: number; appointments_30d: number; risks: string[] }[] };
};
type UpgradeRow = { id: string; clinic_name: string; kind: string; target_code: string; message: string | null; status: string; created_at: string };

export default function PlatformOverview() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [requests, setRequests] = useState<UpgradeRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [summary, pending] = await Promise.all([api<Overview>("/api/v1/admin/overview"), api<UpgradeRow[]>("/api/v1/admin/upgrade-requests?status=pending")]);
      setOverview(summary);
      setRequests(pending ?? []);
    } catch (reason) {
      setError(errorMessage(reason, "The business overview could not be loaded."));
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  async function decide(id: string, decision: "approve" | "decline") {
    const note = decision === "decline" ? window.prompt("Reason for declining (shown to the clinic)") : null;
    if (decision === "decline" && !note) return;
    setBusy(id);
    try {
      await post(`/api/v1/admin/upgrade-requests/${id}/decide`, { decision, note });
      await load();
    } catch (reason) {
      setError(errorMessage(reason, "The decision could not be saved."));
    } finally {
      setBusy(null);
    }
  }

  const subs = overview?.subscriptions;
  return <section className="detail-card admin-panel" id="business" aria-label="Business overview">
    <div className="card-heading"><div><p className="eyebrow">BUSINESS</p><h2>Clients, revenue and upgrades</h2></div><button className="button button-secondary" type="button" onClick={() => void load()}>Refresh <span>↻</span></button></div>
    {error && <div className="workspace-alert" role="alert"><strong>{error}</strong></div>}
    {overview && subs && <>
      <div className="admin-kpis">
        <div><span className="eyebrow">CLIENTS</span><strong>{overview.clinics.total}</strong><small>{overview.clinics.by_status.active ?? 0} ACTIVE · {overview.clinics.by_status.suspended ?? 0} SUSPENDED · +{overview.clinics.onboarded_30d} IN 30D</small></div>
        <div><span className="eyebrow">MRR</span><strong>{money(subs.mrr_minor)}</strong><small>ARR {money(subs.mrr_minor * 12)}</small></div>
        <div><span className="eyebrow">OVERDUE</span><strong>{money(subs.overdue_minor)}</strong><small>{subs.past_due} PAST DUE</small></div>
        <div><span className="eyebrow">RENEWALS · 30D</span><strong>{subs.renewals_30d}</strong><small>{subs.trialing} TRIALS · {subs.trials_ending_14d} ENDING SOON</small></div>
      </div>
      <div className="admin-columns">
        <div><p className="eyebrow">PLANS</p>{overview.plans.map((row) => <div className="report-list-row" key={row.code}><span>{label(row.code)}</span><strong>{row.clinics}</strong></div>)}</div>
        <div><p className="eyebrow">SPECIALTY ADOPTION</p>{overview.modules.length === 0 ? <small className="muted-mono">NONE ENABLED YET</small> : overview.modules.map((row) => <div className="report-list-row" key={row.code}><span>{label(row.code)}</span><strong>{row.clinics}</strong></div>)}</div>
      </div>
      <h3 className="eyebrow admin-subtitle">UPGRADE REQUESTS · {overview.open_upgrade_requests} OPEN</h3>
      {requests.length === 0 ? <div className="dashboard-empty"><strong>No pending requests</strong><span>Clinics ask for locked specialties from their Manage page.</span></div> : <div className="invoice-list">{requests.map((item) => <article className="invoice-row" key={item.id}><div className="invoice-mark">↑</div><div className="invoice-main"><h3>{item.clinic_name}</h3><p>{label(item.kind)} · {item.target_code}{item.message ? ` — ${item.message}` : ""}</p><small>{new Date(item.created_at).toLocaleString()}</small></div><div className="invoice-actions"><button className="button button-primary" disabled={busy === item.id} onClick={() => void decide(item.id, "approve")}>Approve</button><button className="text-control" disabled={busy === item.id} onClick={() => void decide(item.id, "decline")}>Decline</button></div></article>)}</div>}
      <h3 className="eyebrow admin-subtitle">CLIENT HEALTH · {overview.client_health.at_risk.length} AT RISK OF {overview.client_health.checked}</h3>
      {overview.client_health.at_risk.length === 0 ? <div className="dashboard-empty"><strong>No risk signals</strong><span>Every checked clinic has recent logins and appointments.</span></div> : <div className="invoice-list">{overview.client_health.at_risk.map((item) => <article className="invoice-row" key={item.clinic_id}><div className="invoice-mark">!</div><div className="invoice-main"><h3>{item.name}</h3><p>{item.risks.map(label).join(" · ")}</p><small>{item.last_login_at ? `Last login ${new Date(item.last_login_at).toLocaleDateString()}` : "Never logged in"} · {item.active_users} users · {item.appointments_30d} appointments / 30d</small></div></article>)}</div>}
    </>}
  </section>;
}
