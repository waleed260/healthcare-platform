"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";

type Policy = { id: string; name: string; jurisdiction: string; rules: Record<string, unknown>; approved_by: string | null; approved_at: string | null; active: boolean; created_at: string };
type Clinic = { id: string; name: string; slug: string; status: string };

function csrf(): string {
  return document.cookie.split("; ").find((item) => item.startsWith("csrf_token="))?.split("=")[1] ?? "";
}

async function read(response: Response): Promise<any> {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload?.error?.message ?? "The governance workspace could not complete that request.");
  return payload.data;
}

export default function GovernancePage() {
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [clinics, setClinics] = useState<Clinic[]>([]);
  const [selectedClinic, setSelectedClinic] = useState("");
  const [selectedPolicy, setSelectedPolicy] = useState("");
  const [name, setName] = useState("");
  const [jurisdiction, setJurisdiction] = useState("");
  const [rules, setRules] = useState('{"documents":{"retention_days":365}}');
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const [policyResponse, clinicResponse] = await Promise.all([
        fetch("/api/v1/admin/retention-policies", { credentials: "include", cache: "no-store" }),
        fetch("/api/v1/admin/clinics", { credentials: "include", cache: "no-store" }),
      ]);
      const [policyData, clinicData] = await Promise.all([read(policyResponse), read(clinicResponse)]);
      setPolicies((policyData ?? []) as Policy[]); setClinics((clinicData ?? []) as Clinic[]);
      setSelectedClinic((current) => current || clinicData?.[0]?.id || "");
      setSelectedPolicy((current) => current || policyData?.find((item: Policy) => item.active)?.id || "");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "The governance workspace could not be loaded."); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function createPolicy(event: FormEvent) {
    event.preventDefault(); setWorking(true); setError(null); setNotice(null);
    try {
      let parsedRules: Record<string, unknown>;
      try { parsedRules = JSON.parse(rules) as Record<string, unknown>; } catch { throw new Error("Retention rules must be valid JSON."); }
      await read(await fetch("/api/v1/admin/retention-policies", { method: "POST", credentials: "include", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf() }, body: JSON.stringify({ name, jurisdiction, rules: parsedRules }) }));
      setName(""); setJurisdiction(""); setNotice("Policy created inactive. A separate approval is required before assignment."); await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "The policy could not be created."); }
    finally { setWorking(false); }
  }

  async function approvePolicy(policyId: string) {
    setWorking(true); setError(null); setNotice(null);
    try { await read(await fetch(`/api/v1/admin/retention-policies/${policyId}/approve`, { method: "POST", credentials: "include", headers: { "X-CSRF-Token": csrf() } })); setNotice("Policy approved and available for explicit clinic assignment."); await load(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "The policy could not be approved."); }
    finally { setWorking(false); }
  }

  async function assignPolicy(event: FormEvent) {
    event.preventDefault(); setWorking(true); setError(null); setNotice(null);
    try { await read(await fetch(`/api/v1/admin/clinics/${selectedClinic}/retention-policy`, { method: "PUT", credentials: "include", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf() }, body: JSON.stringify({ policy_id: selectedPolicy }) })); setNotice("Approved retention policy assigned to the clinic."); await load(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "The policy could not be assigned."); }
    finally { setWorking(false); }
  }

  return <main className="dashboard-page"><header className="dash-header shell"><Link className="wordmark" href="/">care<span>/</span>fully</Link><div className="clinic-chip" aria-label="Platform governance session"><span className="clinic-avatar">PA</span><span>Platform governance</span></div></header><div className="dashboard shell"><aside className="sidebar"><p className="eyebrow">ADMINISTRATION</p><nav aria-label="Platform navigation"><Link className="side-link" href="/dashboard">◈ <span>Overview</span></Link><Link className="side-link active" href="/admin/governance" aria-current="page">▣ <span>Governance</span></Link></nav></aside><section className="dash-content governance-content" aria-busy={loading}><div className="dash-topline"><div><p className="eyebrow">PLATFORM ADMIN · RETENTION</p><h1>Approve <em>carefully.</em></h1></div><button className="button button-primary" type="button" onClick={() => void load()} disabled={loading}>Refresh <span>↻</span></button></div><p className="queue-intro">Create jurisdiction-specific policies as inactive drafts. Approval and clinic assignment are separate, auditable actions.</p>{error && <div className="workspace-alert" role="alert"><strong>{error}</strong><button className="ghost-button" type="button" onClick={() => void load()}>Try again <span>→</span></button></div>}{notice && <div className="workspace-alert governance-notice" role="status">{notice}</div>}<div className="governance-grid"><form className="detail-card governance-form" onSubmit={createPolicy}><p className="eyebrow">NEW POLICY</p><h2>Draft retention rules</h2><label htmlFor="policy-name">Policy name</label><input id="policy-name" value={name} onChange={(event) => setName(event.target.value)} required maxLength={160} placeholder="Synthetic jurisdiction policy" /><label htmlFor="policy-jurisdiction">Jurisdiction</label><input id="policy-jurisdiction" value={jurisdiction} onChange={(event) => setJurisdiction(event.target.value)} required maxLength={120} placeholder="Jurisdiction under review" /><label htmlFor="policy-rules">Rules JSON</label><textarea id="policy-rules" value={rules} onChange={(event) => setRules(event.target.value)} rows={6} spellCheck={false} /><button className="button button-primary" type="submit" disabled={working}>{working ? "Saving…" : "Create inactive policy"}<span>→</span></button><p className="privacy-caption">This action records a draft only. Legal or jurisdictional approval must be completed by the designated deployment owner.</p></form><section className="detail-card"><div className="card-heading"><div><p className="eyebrow">POLICY REGISTER</p><h2>Retention policies</h2></div><span className="directory-count">{policies.length} shown</span></div>{loading && policies.length === 0 && <div className="dashboard-empty" role="status"><strong>Loading policy register</strong><span>Checking platform-admin scope…</span></div>}{!loading && policies.length === 0 && <div className="dashboard-empty"><strong>No policies yet</strong><span>Create an inactive policy draft for review.</span></div>}{policies.length > 0 && <div className="policy-list" role="list">{policies.map((policy) => <article className="policy-row" key={policy.id} role="listitem"><div><strong>{policy.name}</strong><small>{policy.jurisdiction} · {policy.active ? `approved ${policy.approved_at ? new Date(policy.approved_at).toLocaleDateString() : ""}` : "inactive draft"}</small></div>{policy.active ? <span className="policy-status active">Approved</span> : <button className="button button-secondary" type="button" onClick={() => void approvePolicy(policy.id)} disabled={working}>Approve</button>}</article>)}</div>}</section></div><form className="detail-card governance-assign" onSubmit={assignPolicy}><div className="card-heading"><div><p className="eyebrow">EXPLICIT ASSIGNMENT</p><h2>Attach an approved policy</h2></div></div><div className="governance-assignment-fields"><label htmlFor="policy-select">Approved policy<select id="policy-select" value={selectedPolicy} onChange={(event) => setSelectedPolicy(event.target.value)} required><option value="">Select an approved policy</option>{policies.filter((policy) => policy.active).map((policy) => <option value={policy.id} key={policy.id}>{policy.name} · {policy.jurisdiction}</option>)}</select></label><label htmlFor="clinic-select">Clinic<select id="clinic-select" value={selectedClinic} onChange={(event) => setSelectedClinic(event.target.value)} required><option value="">Select a clinic</option>{clinics.map((clinic) => <option value={clinic.id} key={clinic.id}>{clinic.name} · {clinic.status}</option>)}</select></label><button className="button button-primary" type="submit" disabled={working || !selectedPolicy || !selectedClinic}>Assign policy <span>→</span></button></div></form></section></div></main>;
}
