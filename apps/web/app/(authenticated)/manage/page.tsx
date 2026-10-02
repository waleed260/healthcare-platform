"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { api, errorMessage, label, money, patch, post } from "../_lib/client";

type Session = { permissions?: string[] };
type Service = { id: string; name: string; category: string | null; duration_minutes: number; price_mode: string; amount_minor: number | null; currency: string | null; visibility: string; status: string; version: number };
type Branch = { id: string; code: string; name: string; timezone: string; phone: string | null; status: string; version: number };
type StaffUser = { id: string; display_name: string; normalized_email: string; status: string; last_login_at: string | null; version: number };
type Role = { id: string; name: string; is_system: boolean; permissions: { code: string }[] };
type Specialty = { id: string; code: string; name: string; description: string | null; enabled?: boolean; status?: string };
type Upgrade = { id: string; kind: string; target_code: string; message: string | null; status: string; decision_note: string | null; created_at: string };

const TABS = [
  { id: "services", label: "Services", permission: "service.read" },
  { id: "branches", label: "Branches", permission: "branch.read" },
  { id: "staff", label: "Staff", permission: "staff.read" },
  { id: "roles", label: "Roles", permission: "staff.read" },
  { id: "modules", label: "Specialties & plan", permission: "clinic.read" },
] as const;
type Tab = (typeof TABS)[number]["id"];

export default function ManagePage() {
  const [permissions, setPermissions] = useState<string[]>([]);
  const [tab, setTab] = useState<Tab>("services");
  const [services, setServices] = useState<Service[]>([]);
  const [branches, setBranches] = useState<Branch[]>([]);
  const [staff, setStaff] = useState<StaffUser[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [specialties, setSpecialties] = useState<Specialty[]>([]);
  const [upgrades, setUpgrades] = useState<Upgrade[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const can = useCallback((permission: string) => permissions.includes(permission), [permissions]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const session = await api<Session>("/api/v1/auth/me");
      const granted = session.permissions ?? [];
      setPermissions(granted);
      const has = (code: string) => granted.includes(code);
      const [serviceRows, branchRows, staffRows, roleRows, specialtyRows, upgradeRows] = await Promise.all([
        has("service.read") ? api<Service[]>("/api/v1/services?limit=100") : Promise.resolve([]),
        has("branch.read") ? api<Branch[]>("/api/v1/branches?limit=100") : Promise.resolve([]),
        has("staff.read") ? api<StaffUser[]>("/api/v1/staff/users?limit=100") : Promise.resolve([]),
        has("staff.read") ? api<Role[]>("/api/v1/staff/roles?limit=100") : Promise.resolve([]),
        has("specialty.read") ? api<Specialty[]>("/api/v1/specialties/library") : Promise.resolve([]),
        has("clinic.read") ? api<Upgrade[]>("/api/v1/upgrade-requests") : Promise.resolve([]),
      ]);
      setServices(serviceRows ?? []);
      setBranches(branchRows ?? []);
      setStaff(staffRows ?? []);
      setRoles(roleRows ?? []);
      setSpecialties(specialtyRows ?? []);
      setUpgrades(upgradeRows ?? []);
    } catch (reason) {
      setError(errorMessage(reason, "The admin panel could not be loaded."));
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const visibleTabs = useMemo(() => TABS.filter((item) => permissions.length === 0 || can(item.permission)), [can, permissions.length]);

  async function run(action: () => Promise<unknown>, success: string, fallback: string) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await action();
      setNotice(success);
      setShowForm(false);
      await load();
    } catch (reason) {
      setError(errorMessage(reason, fallback));
    } finally {
      setBusy(false);
    }
  }

  const field = (form: FormData, key: string) => String(form.get(key) ?? "").trim();

  function createService(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const mode = field(form, "price_mode");
    const amount = Math.round(Number(field(form, "amount")) * 100);
    void run(() => post("/api/v1/services", {
      name: field(form, "name"), category: field(form, "category") || null, duration_minutes: Number(field(form, "duration")),
      price_mode: mode, amount_minor: mode === "contact" ? null : amount, currency: mode === "contact" ? null : "PKR", visibility: field(form, "visibility"),
    }), "Service added.", "The service could not be created.");
  }
  function createBranch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    void run(() => post("/api/v1/branches", { code: field(form, "code"), name: field(form, "name"), timezone: field(form, "timezone"), phone: field(form, "phone") || null, address: {} }), "Branch added.", "The branch could not be created.");
  }
  function inviteStaff(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    void run(() => post("/api/v1/staff/invitations", { email: field(form, "email") }), "Invitation sent.", "The invitation could not be sent.");
  }
  function requestAccess(code: string) {
    void run(() => post("/api/v1/upgrade-requests", { kind: "specialty", target_code: code }), "Request sent to the platform team.", "The request could not be sent.");
  }

  const addButton = (text: string, permission: string) => can(permission) && <button className="button button-primary" onClick={() => setShowForm((value) => !value)}>{text} <span>＋</span></button>;

  return <main className="workspace-page manage-page">
    <div className="workspace-page-header"><div><p className="eyebrow">MANAGEMENT · THE CLINIC ITSELF</p><h1>Run the clinic, <em>your way.</em></h1><p className="workspace-page-intro">Services, branches, staff and access in one place. Everything here also powers your website, so it only needs to be entered once.</p></div><div className="header-actions"><button className="button button-secondary" onClick={() => void load()} disabled={loading}>Refresh <span>↻</span></button></div></div>
    {error && <div className="workspace-alert" role="alert"><strong>{error}</strong><button className="ghost-button" onClick={() => void load()}>Try again <span>→</span></button></div>}
    {notice && <div className="permission-strip" role="status"><span className="permission-ok">{notice}</span></div>}
    <div className="pipeline-toolbar"><div className="pipeline-tabs" role="tablist">{visibleTabs.map((item) => <button key={item.id} role="tab" aria-selected={tab === item.id} className={tab === item.id ? "active" : ""} onClick={() => { setTab(item.id); setShowForm(false); }}>{item.label}</button>)}</div></div>

    {tab === "services" && <section className="surface-card">
      <div className="surface-card-heading"><div><p className="eyebrow">SERVICE CATALOG</p><h2>What patients can book.</h2></div>{addButton("Add service", "service.manage")}</div>
      {showForm && <form className="manage-form" onSubmit={createService}><div className="form-grid"><label>Name<input name="name" required maxLength={160} placeholder="HydraFacial" /></label><label>Category <span className="field-optional">optional</span><input name="category" maxLength={120} placeholder="Skin" /></label><label>Duration (min)<input name="duration" type="number" min={5} max={1440} defaultValue={30} required /></label><label>Pricing<select name="price_mode" defaultValue="exact"><option value="exact">Exact price</option><option value="starting_at">Starting at</option><option value="range">Range</option><option value="contact">Contact for price</option></select></label><label>Price (PKR)<input name="amount" type="number" min={0} step="0.01" defaultValue={0} /></label><label>Website<select name="visibility" defaultValue="public"><option value="public">Visible</option><option value="hidden">Hidden</option></select></label></div><div className="form-actions"><button className="button button-primary" type="submit" disabled={busy}>{busy ? "Saving…" : "Save service"}<span>↗</span></button></div></form>}
      <div className="invoice-list">{!loading && services.length === 0 && <div className="dashboard-empty"><strong>No services yet</strong><span>Add one here or import from the master catalog.</span></div>}{services.map((item) => <article className="invoice-row" key={item.id}><div className="invoice-mark">{item.name.slice(0, 2).toUpperCase()}</div><div className="invoice-main"><h3>{item.name}</h3><p>{item.category ?? "General"} · {item.duration_minutes} min · {item.price_mode === "contact" || item.amount_minor == null ? "Contact for price" : money(item.amount_minor, item.currency ?? "PKR")}</p></div><div className="invoice-actions"><span className={`pipeline-status status-${item.status === "active" ? "paid" : "void"}`}>{item.status}</span>{can("service.manage") && <button className="text-control" disabled={busy} onClick={() => void run(() => patch(`/api/v1/services/${item.id}`, { expected_version: item.version, visibility: item.visibility === "public" ? "hidden" : "public" }), "Visibility updated.", "The service could not be updated.")}>{item.visibility === "public" ? "Hide from website" : "Show on website"}</button>}</div></article>)}</div>
    </section>}

    {tab === "branches" && <section className="surface-card">
      <div className="surface-card-heading"><div><p className="eyebrow">LOCATIONS</p><h2>Where care happens.</h2></div>{addButton("Add branch", "branch.manage")}</div>
      {showForm && <form className="manage-form" onSubmit={createBranch}><div className="form-grid"><label>Code<input name="code" required maxLength={40} placeholder="MAIN" /></label><label>Name<input name="name" required maxLength={160} placeholder="Main branch" /></label><label>Timezone<input name="timezone" required defaultValue="Asia/Karachi" /></label><label>Phone <span className="field-optional">optional</span><input name="phone" maxLength={40} /></label></div><div className="form-actions"><button className="button button-primary" type="submit" disabled={busy}>{busy ? "Saving…" : "Save branch"}<span>↗</span></button></div></form>}
      <div className="invoice-list">{!loading && branches.length === 0 && <div className="dashboard-empty"><strong>No branches yet</strong><span>Add your first location.</span></div>}{branches.map((item) => <article className="invoice-row" key={item.id}><div className="invoice-mark">{item.code.slice(0, 3)}</div><div className="invoice-main"><h3>{item.name}</h3><p>{item.timezone}{item.phone ? ` · ${item.phone}` : ""}</p></div><div className="invoice-actions"><span className={`pipeline-status status-${item.status === "active" ? "paid" : "void"}`}>{item.status}</span></div></article>)}</div>
    </section>}

    {tab === "staff" && <section className="surface-card">
      <div className="surface-card-heading"><div><p className="eyebrow">TEAM</p><h2>Invite, don’t share logins.</h2></div>{addButton("Invite staff", "staff.manage")}</div>
      {showForm && <form className="manage-form" onSubmit={inviteStaff}><div className="form-grid"><label>Email<input name="email" type="email" required placeholder="doctor@clinic.com" /></label></div><div className="form-actions"><button className="button button-primary" type="submit" disabled={busy}>{busy ? "Sending…" : "Send invitation"}<span>↗</span></button></div></form>}
      <div className="invoice-list">{!loading && staff.length === 0 && <div className="dashboard-empty"><strong>No staff yet</strong><span>Invited team members appear here once they accept.</span></div>}{staff.map((item) => <article className="invoice-row" key={item.id}><div className="invoice-mark">{item.display_name.slice(0, 2).toUpperCase()}</div><div className="invoice-main"><h3>{item.display_name}</h3><p>{item.normalized_email}</p><small>{item.last_login_at ? `Last sign-in ${new Date(item.last_login_at).toLocaleDateString()}` : "Never signed in"}</small></div><div className="invoice-actions"><span className={`pipeline-status status-${item.status === "active" ? "paid" : "void"}`}>{item.status}</span>{can("staff.manage") && <button className="text-control" disabled={busy} onClick={() => void run(() => post(`/api/v1/staff/users/${item.id}/status`, { expected_version: item.version, status: item.status === "active" ? "suspended" : "active" }), "Staff status updated.", "The status could not be changed.")}>{item.status === "active" ? "Suspend" : "Reactivate"}</button>}</div></article>)}</div>
    </section>}

    {tab === "roles" && <section className="surface-card">
      <div className="surface-card-heading"><div><p className="eyebrow">ACCESS</p><h2>What each role can do.</h2></div></div>
      <div className="invoice-list">{roles.map((role) => <article className="invoice-row" key={role.id}><div className="invoice-mark">{role.name.slice(0, 2).toUpperCase()}</div><div className="invoice-main"><h3>{label(role.name)}</h3><p>{role.permissions.length} permissions{role.is_system ? " · system role" : ""}</p><small>{role.permissions.slice(0, 8).map((item) => item.code).join(" · ")}{role.permissions.length > 8 ? " …" : ""}</small></div></article>)}</div>
    </section>}

    {tab === "modules" && <section className="surface-card">
      <div className="surface-card-heading"><div><p className="eyebrow">SPECIALTIES</p><h2>Grow without migrating.</h2></div></div>
      <div className="invoice-list">{specialties.map((item) => <article className="invoice-row" key={item.id}><div className="invoice-mark">{item.code.slice(0, 3).toUpperCase()}</div><div className="invoice-main"><h3>{item.name}</h3><p>{item.description}</p></div><div className="invoice-actions">{item.enabled ? <span className="pipeline-status status-paid">Enabled</span> : upgrades.some((request) => request.kind === "specialty" && request.target_code === item.code && request.status === "pending") ? <span className="pipeline-status status-contacted">Request pending</span> : can("clinic.update") ? <button className="button button-secondary" disabled={busy} onClick={() => requestAccess(item.code)}>Request access</button> : <span className="pipeline-status status-void">Locked</span>}</div></article>)}</div>
      {upgrades.length > 0 && <><div className="surface-card-heading manage-subhead"><div><p className="eyebrow">REQUEST HISTORY</p></div></div><div className="invoice-list">{upgrades.map((item) => <article className="invoice-row" key={item.id}><div className="invoice-mark">↑</div><div className="invoice-main"><h3>{label(item.kind)} · {item.target_code}</h3><p>{item.decision_note ?? item.message ?? "Awaiting review"}</p><small>{new Date(item.created_at).toLocaleString()}</small></div><div className="invoice-actions"><span className={`pipeline-status status-${item.status === "approved" ? "paid" : item.status === "pending" ? "contacted" : "void"}`}>{item.status}</span>{item.status === "pending" && can("clinic.update") && <button className="text-control" disabled={busy} onClick={() => void run(() => post(`/api/v1/upgrade-requests/${item.id}/cancel`), "Request cancelled.", "The request could not be cancelled.")}>Cancel</button>}</div></article>)}</div></>}
    </section>}
  </main>;
}
