"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import anime from "animejs";
import { api, errorMessage, post, writeHeaders } from "../../_lib/client";

type Policy = { id: string; name: string; jurisdiction: string; rules: Record<string, unknown>; approved_by: string | null; approved_at: string | null; active: boolean; created_at: string };
type Clinic = { id: string; name: string; slug: string; status: string };

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
      const [policyData, clinicData] = await Promise.all([
        api<Policy[]>("/api/v1/admin/retention-policies").catch(() => [] as Policy[]),
        api<Clinic[]>("/api/v1/admin/clinics").catch(() => [] as Clinic[]),
      ]);
      const pList = policyData ?? []; const cList = clinicData ?? [];
      setPolicies(pList); setClinics(cList);
      setSelectedClinic((current) => current || cList[0]?.id || "");
      setSelectedPolicy((current) => current || pList.find((item) => item.active)?.id || "");
    } catch (reason) { setError(errorMessage(reason, "The governance workspace could not be loaded.")); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function createPolicy(event: FormEvent) {
    event.preventDefault(); setWorking(true); setError(null); setNotice(null);
    try {
      let parsedRules: Record<string, unknown>;
      try { parsedRules = JSON.parse(rules) as Record<string, unknown>; } catch { throw new Error("Retention rules must be valid JSON."); }
      await post("/api/v1/admin/retention-policies", { name, jurisdiction, rules: parsedRules });
      setName(""); setJurisdiction(""); setNotice("Policy created inactive. A separate approval is required before assignment."); await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "The policy could not be created."); }
    finally { setWorking(false); }
  }

  async function approvePolicy(policyId: string) {
    setWorking(true); setError(null); setNotice(null);
    try { await post(`/api/v1/admin/retention-policies/${policyId}/approve`); setNotice("Policy approved and available for explicit clinic assignment."); await load(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "The policy could not be approved."); }
    finally { setWorking(false); }
  }

  async function assignPolicy(event: FormEvent) {
    event.preventDefault(); setWorking(true); setError(null); setNotice(null);
    try { await api(`/api/v1/admin/clinics/${selectedClinic}/retention-policy`, { method: "PUT", headers: writeHeaders(), body: JSON.stringify({ policy_id: selectedPolicy }) }); setNotice("Approved retention policy assigned to the clinic."); await load(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "The policy could not be assigned."); }
    finally { setWorking(false); }
  }

  const contentRef = useRef<HTMLElement>(null);
  useEffect(() => {
    if (!contentRef.current) return;
    anime({ targets: contentRef.current.querySelectorAll(".surface-card, .detail-card, .inventory-summary > div"), opacity: [0, 1], translateY: [22, 0], duration: 500, delay: anime.stagger(50, { start: 120 }), easing: "easeOutCubic" });
  }, []);

  return <main className="workspace-page governance-content" aria-busy={loading} ref={contentRef}>
    <div className="workspace-page-header"><div><p className="eyebrow">PLATFORM ADMIN · RETENTION</p><h1>Approve <em>carefully.</em></h1><p className="workspace-page-intro">Create jurisdiction-specific policies as inactive drafts. Approval and clinic assignment are separate, auditable actions.</p></div><button className="button button-primary" type="button" onClick={() => void load()} disabled={loading}>Refresh <span>↻</span></button></div>
    {error && <div className="workspace-alert" role="alert"><strong>{error}</strong><button className="ghost-button" type="button" onClick={() => void load()}>Try again <span>→</span></button></div>}
    {notice && <div className="workspace-alert governance-notice" role="status">{notice}</div>}

    <div className="inventory-summary" style={{ marginBottom: 20 }}>
      <div><span className="eyebrow">POLICIES</span><strong>{policies.length}</strong><small>{policies.filter((p) => p.active).length} approved</small></div>
      <div><span className="eyebrow">CLINICS</span><strong>{clinics.length}</strong><small>available for assignment</small></div>
    </div>

    <div className="governance-grid">
      <form className="surface-card governance-form" onSubmit={createPolicy}><div className="surface-card-heading"><div><p className="eyebrow">NEW POLICY</p><h2>Draft retention rules</h2></div></div>
        <div className="manage-form"><div className="form-grid"><label htmlFor="policy-name">Policy name<input id="policy-name" value={name} onChange={(event) => setName(event.target.value)} required maxLength={160} placeholder="Synthetic jurisdiction policy" /></label><label htmlFor="policy-jurisdiction">Jurisdiction<input id="policy-jurisdiction" value={jurisdiction} onChange={(event) => setJurisdiction(event.target.value)} required maxLength={120} placeholder="Jurisdiction under review" /></label></div><label htmlFor="policy-rules" className="font-field">Rules JSON<textarea id="policy-rules" value={rules} onChange={(event) => setRules(event.target.value)} rows={6} spellCheck={false} /></label><div className="form-actions"><button className="button button-primary" type="submit" disabled={working}>{working ? "Saving…" : "Create inactive policy"} <span>→</span></button></div><p className="privacy-caption">This action records a draft only. Legal or jurisdictional approval must be completed by the designated deployment owner.</p></div>
      </form>

      <section className="surface-card"><div className="surface-card-heading"><div><p className="eyebrow">POLICY REGISTER</p><h2>Retention policies</h2></div><span className="directory-count">{policies.length} shown</span></div>
        {loading && policies.length === 0 && <div className="dashboard-empty" role="status"><strong>Loading policy register</strong><span>Checking platform-admin scope…</span></div>}
        {!loading && policies.length === 0 && <div className="dashboard-empty"><strong>No policies yet</strong><span>Create an inactive policy draft for review.</span></div>}
        {policies.length > 0 && <div className="invoice-list" role="list">{policies.map((policy) => <article className="invoice-row" key={policy.id} role="listitem"><div className="invoice-mark">{policy.active ? "✓" : "○"}</div><div className="invoice-main"><h3>{policy.name}</h3><p>{policy.jurisdiction} · {policy.active ? `approved ${policy.approved_at ? new Date(policy.approved_at).toLocaleDateString() : ""}` : "inactive draft"}</p></div><div className="invoice-actions">{policy.active ? <span className="pipeline-status status-paid">Approved</span> : <button className="button button-secondary" type="button" onClick={() => void approvePolicy(policy.id)} disabled={working}>Approve</button>}</div></article>)}</div>}
      </section>
    </div>

    <form className="surface-card governance-assign" onSubmit={assignPolicy}><div className="surface-card-heading"><div><p className="eyebrow">EXPLICIT ASSIGNMENT</p><h2>Attach an approved policy</h2></div></div>
      <div className="manage-form"><div className="form-grid"><label htmlFor="policy-select">Approved policy<select id="policy-select" value={selectedPolicy} onChange={(event) => setSelectedPolicy(event.target.value)} required><option value="">Select an approved policy</option>{policies.filter((policy) => policy.active).map((policy) => <option value={policy.id} key={policy.id}>{policy.name} · {policy.jurisdiction}</option>)}</select></label><label htmlFor="clinic-select">Clinic<select id="clinic-select" value={selectedClinic} onChange={(event) => setSelectedClinic(event.target.value)} required><option value="">Select a clinic</option>{clinics.map((clinic) => <option value={clinic.id} key={clinic.id}>{clinic.name} · {clinic.status}</option>)}</select></label></div><div className="form-actions"><button className="button button-primary" type="submit" disabled={working || !selectedPolicy || !selectedClinic}>Assign policy <span>→</span></button></div></div>
    </form>
  </main>;
}
