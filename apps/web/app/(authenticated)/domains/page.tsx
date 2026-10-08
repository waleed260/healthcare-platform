"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import anime from "animejs";
import { api, errorMessage, label, post } from "../_lib/client";
import { useToast } from "../_lib/toast";
import { useConfirm } from "../_lib/confirm";
import Drawer from "../_lib/drawer";

type Domain = { id: string; hostname: string; observed_status: string; certificate_status: string | null; checked_at: string | null; failure_reason: string | null; created_at: string };
type DomainWithProof = Domain & { dns_proof?: string; dns_record_name?: string };
type Session = { permissions?: string[] };

function date(value: string): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

const statusIcon: Record<string, string> = { verified: "●", pending: "○", failed: "✕" };
const statusColor: Record<string, string> = { verified: "status-paid", pending: "status-pending", failed: "status-lost" };

export default function DomainsPage() {
  const [domains, setDomains] = useState<Domain[]>([]);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [hostname, setHostname] = useState("");
  const [proof, setProof] = useState<DomainWithProof | null>(null);
  const [verifyDrawer, setVerifyDrawer] = useState<Domain | null>(null);
  const [observedProof, setObservedProof] = useState("");
  const toast = useToast();
  const confirm = useConfirm();
  const can = (p: string) => permissions.includes(p);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [session, domainData] = await Promise.all([
        api<Session>("/api/v1/auth/me"),
        api<Domain[]>("/api/v1/websites/domains?limit=50"),
      ]);
      setPermissions(session.permissions ?? []);
      setDomains(domainData ?? []);
    } catch (reason) {
      setError(errorMessage(reason, "Domains could not be loaded."));
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  async function addDomain(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    try {
      const result = await post<DomainWithProof>("/api/v1/websites/domains", { hostname: hostname.trim().toLowerCase() });
      setProof(result);
      setHostname("");
      setShowAdd(false);
      toast.success("Domain registered. Add the DNS record shown below, then verify.");
      await load();
    } catch (reason) {
      toast.error(errorMessage(reason, "The domain could not be added."));
    } finally {
      setBusy(false);
    }
  }

  async function verifyDomain(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!verifyDrawer) return;
    setBusy(true);
    try {
      await post(`/api/v1/websites/domains/${verifyDrawer.id}/verify`, { observed_proof: observedProof.trim() });
      toast.success("Domain verified! Certificate provisioning will begin shortly.");
      setVerifyDrawer(null);
      setObservedProof("");
      await load();
    } catch (reason) {
      toast.error(errorMessage(reason, "Verification failed. Check that the DNS record is in place."));
    } finally {
      setBusy(false);
    }
  }

  const verified = domains.filter((d) => d.observed_status === "verified").length;
  const pending = domains.filter((d) => d.observed_status === "pending").length;

  const domainListRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (loading || domains.length === 0 || !domainListRef.current) return;
    anime({
      targets: domainListRef.current.querySelectorAll(".invoice-row"),
      opacity: [0, 1],
      translateX: [-14, 0],
      duration: 440,
      delay: anime.stagger(50, { start: 100 }),
      easing: "easeOutCubic",
    });
  }, [loading, domains.length]);

  return <main className="workspace-page domains-page">
    <div className="workspace-page-header">
      <div>
        <p className="eyebrow">WEBSITE · DOMAINS</p>
        <h1>Your clinic's <em>address.</em></h1>
        <p className="workspace-page-intro">Connect custom domains, verify DNS ownership, and manage certificates for your published website.</p>
      </div>
      <div className="header-actions">
        <button className="button button-secondary" onClick={() => void load()} disabled={loading}>Refresh <span>↻</span></button>
        {can("website.edit") && <button className="button button-primary" onClick={() => setShowAdd((v) => !v)}>Add domain <span>＋</span></button>}
      </div>
    </div>

    {error && <div className="workspace-alert" role="alert"><strong>{error}</strong><button className="ghost-button" onClick={() => void load()}>Try again <span>→</span></button></div>}

    <div className="inventory-summary" style={{ marginBottom: 20 }}>
      <div className="inventory-summary-dark"><span className="eyebrow">VERIFIED</span><strong>{verified}</strong><small>domains connected</small></div>
      <div><span className="eyebrow">PENDING</span><strong>{pending}</strong><small>awaiting DNS verification</small></div>
      <div><span className="eyebrow">TOTAL</span><strong>{domains.length}</strong><small>registered domains</small></div>
    </div>

    {/* DNS proof alert — shown after adding a domain */}
    {proof?.dns_proof && <div className="surface-card" style={{ marginBottom: 16, padding: 20 }}>
      <div className="surface-card-heading"><div><p className="eyebrow">DNS SETUP REQUIRED</p><h2>Add this TXT record to verify <strong>{proof.hostname}</strong></h2></div></div>
      <div style={{ padding: "12px 0" }}>
        <p style={{ fontSize: "0.85rem", marginBottom: 8 }}>Add a TXT record to your domain's DNS settings:</p>
        <div style={{ display: "grid", gap: 8, fontSize: "0.82rem" }}>
          <label style={{ fontWeight: 600 }}>Record name<code style={{ display: "block", padding: "8px 12px", background: "var(--surface-2, #f5f5f0)", borderRadius: 6, marginTop: 4, wordBreak: "break-all" }}>{proof.dns_record_name}</code></label>
          <label style={{ fontWeight: 600 }}>Record value<code style={{ display: "block", padding: "8px 12px", background: "var(--surface-2, #f5f5f0)", borderRadius: 6, marginTop: 4, wordBreak: "break-all" }}>{proof.dns_proof}</code></label>
        </div>
        <p style={{ fontSize: "0.78rem", opacity: 0.6, marginTop: 12 }}>This proof is shown only once. Save it before leaving this page. After adding the record, click "Verify" on the domain below.</p>
      </div>
      <button className="button button-secondary" onClick={() => setProof(null)}>Dismiss</button>
    </div>}

    {/* Add domain form */}
    {showAdd && <form className="surface-card" style={{ marginBottom: 16, padding: 20 }} onSubmit={addDomain}>
      <div className="surface-card-heading"><div><p className="eyebrow">NEW DOMAIN</p><h2>Register a hostname</h2></div></div>
      <div className="form-grid">
        <label>Hostname<input value={hostname} onChange={(e) => setHostname(e.target.value)} required placeholder="clinic.example.com" pattern="[a-zA-Z0-9][a-zA-Z0-9\-.]*\.[a-zA-Z]{2,}" /></label>
      </div>
      <div className="form-actions">
        <button className="button button-secondary" type="button" onClick={() => setShowAdd(false)}>Cancel</button>
        <button className="button button-primary" type="submit" disabled={busy}>{busy ? "Registering…" : "Register domain"} <span>→</span></button>
      </div>
    </form>}

    {loading && domains.length === 0 && <div className="dashboard-empty" role="status"><strong>Loading domains</strong><span>Checking your registered hostnames…</span></div>}

    {/* Domain list */}
    <section className="surface-card">
      <div className="surface-card-heading">
        <div><p className="eyebrow">REGISTERED DOMAINS</p><h2>Connected hostnames</h2></div>
        <span className="muted-mono">{domains.length} DOMAIN{domains.length !== 1 ? "S" : ""}</span>
      </div>
      {!loading && domains.length === 0 && <div className="dashboard-empty"><strong>No domains yet</strong><span>Add a custom domain to serve your website on your own hostname.</span></div>}
      {domains.length > 0 && <div className="invoice-list" ref={domainListRef}>
        {domains.map((item) => <article className="invoice-row" key={item.id}>
          <div className="invoice-mark" style={{ fontSize: "1rem" }}>{statusIcon[item.observed_status] ?? "○"}</div>
          <div className="invoice-main">
            <h3>{item.hostname}</h3>
            <p>
              <span className={`pipeline-status ${statusColor[item.observed_status] ?? ""}`}>{label(item.observed_status)}</span>
              {item.certificate_status && <> · Certificate: {label(item.certificate_status)}</>}
            </p>
            <small>
              Added {date(item.created_at)}
              {item.checked_at && ` · Last checked ${date(item.checked_at)}`}
              {item.failure_reason && ` · ${item.failure_reason}`}
            </small>
          </div>
          <div className="invoice-actions">
            {item.observed_status === "pending" && can("website.edit") && <button className="button button-secondary" style={{ fontSize: "0.78rem", padding: "4px 10px" }} disabled={busy} onClick={() => { setVerifyDrawer(item); setObservedProof(""); }}>Verify</button>}
            {item.observed_status === "verified" && item.certificate_status === "active" && <span className="pipeline-status status-paid">LIVE</span>}
          </div>
        </article>)}
      </div>}
    </section>

    {/* Verify drawer */}
    <Drawer open={!!verifyDrawer} onClose={() => setVerifyDrawer(null)} title="Verify domain" subtitle={verifyDrawer?.hostname}>
      {verifyDrawer && <form onSubmit={verifyDomain}>
        <p style={{ fontSize: "0.85rem", marginBottom: 16 }}>Enter the DNS proof value you added as a TXT record. The server will look it up to confirm ownership.</p>
        <div className="form-grid">
          <label>DNS proof value<input value={observedProof} onChange={(e) => setObservedProof(e.target.value)} required placeholder="Paste the proof token" /></label>
        </div>
        <div className="form-actions" style={{ marginTop: 16 }}>
          <button className="button button-primary" type="submit" disabled={busy || !observedProof.trim()}>{busy ? "Verifying…" : "Verify ownership"} <span>→</span></button>
        </div>
      </form>}
    </Drawer>
  </main>;
}
