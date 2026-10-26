"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { api, errorMessage, label, money, patch, post, writeHeaders } from "../_lib/client";
import Drawer from "../_lib/drawer";
import { useToast } from "../_lib/toast";
import { useConfirm } from "../_lib/confirm";
import { useClinicCurrency } from "../_lib/clinic-context";

type Session = { user_id?: string; permissions?: string[] };
type Service = { id: string; name: string; category: string | null; short_description: string | null; full_description: string | null; duration_minutes: number; buffer_before_minutes: number; buffer_after_minutes: number; price_mode: string; amount_minor: number | null; currency: string | null; approval_mode: string; visibility: string; status: string; version: number };
type ServiceTemplate = { id: string; name: string; category: string | null; specialty_code: string | null; duration_minutes: number; amount_minor: number | null; currency: string | null };
type Branch = { id: string; code: string; name: string; timezone: string; phone: string | null; status: string; version: number };
type StaffUser = { id: string; display_name: string; normalized_email: string; status: string; last_login_at: string | null; version: number; roles?: { id: string; name: string }[]; branch_scopes?: { id: string; name: string }[] };
type Role = { id: string; name: string; is_system: boolean; permissions: { code: string }[] };
type Specialty = { id: string; code: string; name: string; description: string | null; enabled?: boolean; status?: string };
type Upgrade = { id: string; kind: string; target_code: string; message: string | null; status: string; decision_note: string | null; created_at: string };
type Invitation = { id: string; email: string; status: string; created_at: string };
type FeatureLimit = { feature: string; current_usage: number; limit_value: number };
type Subscription = { id: string; code: string; name: string; status: string; starts_at: string | null; ends_at: string | null } | null;

const TABS = [
  { id: "services", label: "Services", permission: "service.read" },
  { id: "staff", label: "Staff", permission: "staff.read" },
  { id: "roles", label: "Roles", permission: "staff.read" },
  { id: "modules", label: "Specialties & Plan", permission: "clinic.read" },
] as const;
type Tab = (typeof TABS)[number]["id"];

const SERVICE_CATEGORIES = ["General", "Skin", "Hair", "Dental", "Dermatology", "Laser", "Injectable", "Surgery", "Consultation", "Lab", "Imaging"];

export default function ManagePage() {
  const clinicCurrency = useClinicCurrency();
  const [permissions, setPermissions] = useState<string[]>([]);
  const [tab, setTab] = useState<Tab>("services");
  const [services, setServices] = useState<Service[]>([]);
  const [templates, setTemplates] = useState<ServiceTemplate[]>([]);
  const [branches, setBranches] = useState<Branch[]>([]);
  const [staff, setStaff] = useState<StaffUser[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [specialties, setSpecialties] = useState<Specialty[]>([]);
  const [upgrades, setUpgrades] = useState<Upgrade[]>([]);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [featureLimits, setFeatureLimits] = useState<FeatureLimit[]>([]);
  const [subscription, setSubscription] = useState<Subscription>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [serviceDrawer, setServiceDrawer] = useState(false);
  const [editService, setEditService] = useState<Service | null>(null);
  const [importDrawer, setImportDrawer] = useState(false);
  const [staffDrawer, setStaffDrawer] = useState(false);
  const [staffDetail, setStaffDetail] = useState<StaffUser | null>(null);
  const [roleDetail, setRoleDetail] = useState<Role | null>(null);
  const [roleDrawer, setRoleDrawer] = useState(false);
  const [editRole, setEditRole] = useState<Role | null>(null);
  const [allPermissions, setAllPermissions] = useState<{ code: string; description: string }[]>([]);

  const [currentUserId, setCurrentUserId] = useState<string | null>(null);
  const [serviceFilter, setServiceFilter] = useState<string>("all");
  const [serviceSearch, setServiceSearch] = useState("");

  const toast = useToast();
  const confirm = useConfirm();
  const can = useCallback((permission: string) => permissions.includes(permission), [permissions]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const session = await api<Session>("/api/v1/auth/me");
      const granted = session.permissions ?? [];
      setPermissions(granted);
      if (session.user_id) setCurrentUserId(session.user_id);
      const has = (code: string) => granted.includes(code);
      const [serviceRows, branchRows, staffRows, roleRows, specialtyRows, upgradeRows, templateRows, inviteRows, limitRows, subscriptionRow, permRows] = await Promise.all([
        has("service.read") ? api<Service[]>("/api/v1/services?limit=100") : Promise.resolve([]),
        has("branch.read") ? api<Branch[]>("/api/v1/branches?limit=100") : Promise.resolve([]),
        has("staff.read") ? api<StaffUser[]>("/api/v1/staff/users?limit=100") : Promise.resolve([]),
        has("staff.read") ? api<Role[]>("/api/v1/staff/roles?limit=100") : Promise.resolve([]),
        has("specialty.read") ? api<Specialty[]>("/api/v1/specialties/library") : Promise.resolve([]),
        has("clinic.read") ? api<Upgrade[]>("/api/v1/upgrade-requests") : Promise.resolve([]),
        has("service.manage") ? api<ServiceTemplate[]>("/api/v1/catalog/service-templates?limit=100").catch(() => []) : Promise.resolve([]),
        has("staff.manage") ? api<Invitation[]>("/api/v1/staff/invitations?limit=50").catch(() => []) : Promise.resolve([]),
        has("clinic.read") ? api<FeatureLimit[]>("/api/v1/governance/feature-limits").catch(() => []) : Promise.resolve([]),
        has("admin.plan.manage") ? api<Subscription>("/api/v1/governance/subscription").catch(() => null) : Promise.resolve(null),
        has("staff.read") ? api<{ code: string; description: string }[]>("/api/v1/staff/permissions").catch(() => []) : Promise.resolve([]),
      ]);
      setServices(serviceRows ?? []);
      setBranches(branchRows ?? []);
      setStaff(staffRows ?? []);
      setRoles(roleRows ?? []);
      setSpecialties(specialtyRows ?? []);
      setUpgrades(upgradeRows ?? []);
      setTemplates(templateRows ?? []);
      setInvitations(inviteRows ?? []);
      setFeatureLimits(limitRows ?? []);
      setSubscription(subscriptionRow ?? null);
      setAllPermissions(permRows ?? []);
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
    try {
      await action();
      toast.success(success);
      await load();
    } catch (reason) {
      toast.error(errorMessage(reason, fallback));
    } finally {
      setBusy(false);
    }
  }

  const field = (form: FormData, key: string) => String(form.get(key) ?? "").trim();

  const filteredServices = useMemo(() => {
    let result = services;
    if (serviceFilter !== "all") {
      result = result.filter((s) => (s.category ?? "General").toLowerCase() === serviceFilter.toLowerCase());
    }
    if (serviceSearch) {
      const q = serviceSearch.toLowerCase();
      result = result.filter((s) => s.name.toLowerCase().includes(q) || (s.category ?? "").toLowerCase().includes(q));
    }
    return result;
  }, [services, serviceFilter, serviceSearch]);

  const categories = useMemo(() => {
    const cats = new Set(services.map((s) => s.category ?? "General"));
    return Array.from(cats).sort();
  }, [services]);

  // ── Service CRUD ──

  function handleServiceSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const mode = field(form, "price_mode");
    const amount = Math.round(Number(field(form, "amount")) * 100);
    const body: Record<string, unknown> = {
      name: field(form, "name"),
      category: field(form, "category") || null,
      short_description: field(form, "short_description") || null,
      duration_minutes: Number(field(form, "duration")),
      buffer_before_minutes: Number(field(form, "buffer_before") || 0),
      buffer_after_minutes: Number(field(form, "buffer_after") || 0),
      price_mode: mode,
      amount_minor: mode === "contact" ? null : amount,
      currency: mode === "contact" ? null : clinicCurrency,
      approval_mode: field(form, "approval_mode"),
      visibility: field(form, "visibility"),
    };

    if (editService) {
      void run(
        () => patch(`/api/v1/services/${editService.id}`, { expected_version: editService.version, ...body }),
        "Service updated.", "The service could not be updated."
      ).then(() => { setEditService(null); setServiceDrawer(false); });
    } else {
      void run(
        () => post("/api/v1/services", body),
        "Service added.", "The service could not be created."
      ).then(() => setServiceDrawer(false));
    }
  }

  function duplicateService(service: Service) {
    void run(
      () => post("/api/v1/services", {
        name: `${service.name} (copy)`, category: service.category, short_description: service.short_description,
        duration_minutes: service.duration_minutes, buffer_before_minutes: service.buffer_before_minutes,
        buffer_after_minutes: service.buffer_after_minutes, price_mode: service.price_mode,
        amount_minor: service.amount_minor, currency: service.currency, approval_mode: service.approval_mode,
        visibility: service.visibility,
      }),
      "Service duplicated.", "The service could not be duplicated."
    );
  }

  async function toggleServiceStatus(service: Service) {
    const newStatus = service.status === "active" ? "archived" : "active";
    const ok = await confirm({ message: `${newStatus === "archived" ? "Deactivate" : "Reactivate"} "${service.name}"?`, danger: newStatus === "archived" });
    if (!ok) return;
    void run(
      () => post(`/api/v1/services/${service.id}/status`, { status: newStatus }),
      `Service ${newStatus === "archived" ? "deactivated" : "reactivated"}.`,
      "The status could not be changed."
    );
  }

  function importTemplate(template: ServiceTemplate) {
    void run(
      () => post("/api/v1/services/from-template", { template_id: template.id }),
      `"${template.name}" imported.`, "The template could not be imported."
    ).then(() => setImportDrawer(false));
  }

  // ── Staff ──

  function handleInvite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true); setError(null);
    post<{ setup_url: string }>("/api/v1/staff/invitations", { email: field(form, "email") })
      .then(async (result) => {
        const url = result?.setup_url ?? "";
        if (url) {
          try { await navigator.clipboard.writeText(url); } catch { /* clipboard unavailable */ }
          toast.success(`Invitation sent. Setup link${url ? " copied to clipboard." : " created."}`);
        } else {
          toast.success("Invitation sent.");
        }
        setStaffDrawer(false);
        await load();
      })
      .catch((reason) => { toast.error(errorMessage(reason, "The invitation could not be sent.")); })
      .finally(() => { setBusy(false); });
  }

  async function revokeInvitation(invitationId: string) {
    const ok = await confirm({ message: "Cancel this invitation? The invite link will stop working.", danger: true });
    if (!ok) return;
    void run(
      () => api(`/api/v1/staff/invitations/${invitationId}`, { method: "DELETE", headers: writeHeaders() }),
      "Invitation cancelled.", "The invitation could not be cancelled."
    );
  }

  async function loadStaffDetail(user: StaffUser) {
    try {
      const [userRoles, userScopes] = await Promise.all([
        api<{ id: string; name: string }[]>(`/api/v1/staff/users/${user.id}/roles`),
        api<{ id: string; name: string }[]>(`/api/v1/staff/users/${user.id}/branch-scopes`),
      ]);
      setStaffDetail({ ...user, roles: userRoles ?? [], branch_scopes: userScopes ?? [] });
    } catch {
      setStaffDetail({ ...user, roles: [], branch_scopes: [] });
    }
  }

  async function assignRole(userId: string, roleId: string) {
    await run(
      () => post(`/api/v1/staff/users/${userId}/roles`, { role_id: roleId }),
      "Role assigned.", "The role could not be assigned."
    );
    if (staffDetail) void loadStaffDetail(staffDetail);
  }

  async function removeRole(userId: string, roleId: string) {
    await run(
      () => api(`/api/v1/staff/users/${userId}/roles/${roleId}`, { method: "DELETE", headers: writeHeaders() }),
      "Role removed.", "The role could not be removed."
    );
    if (staffDetail) void loadStaffDetail(staffDetail);
  }

  async function assignBranchScope(userId: string, branchId: string) {
    await run(
      () => post(`/api/v1/staff/users/${userId}/branch-scopes`, { branch_id: branchId }),
      "Branch scope assigned.", "The scope could not be assigned."
    );
    if (staffDetail) void loadStaffDetail(staffDetail);
  }

  async function removeBranchScope(userId: string, branchId: string) {
    await run(
      () => api(`/api/v1/staff/users/${userId}/branch-scopes/${branchId}`, { method: "DELETE", headers: writeHeaders() }),
      "Branch scope removed.", "The scope could not be removed."
    );
    if (staffDetail) void loadStaffDetail(staffDetail);
  }

  async function resetStaffPassword(user: StaffUser) {
    const ok = await confirm({ message: `Send a password reset for ${user.display_name}?` });
    if (!ok) return;
    void run(
      () => post(`/api/v1/staff/users/${user.id}/manual-reset`, { reason: "Admin-initiated reset" }),
      "Reset link sent.", "The reset could not be triggered."
    );
  }

  function requestAccess(code: string) {
    void run(() => post("/api/v1/upgrade-requests", { kind: "specialty", target_code: code }), "Request sent to the platform team.", "The request could not be sent.");
  }

  // ── Render ──
  return <main className="workspace-page manage-page">
    <div className="workspace-page-header"><div><p className="eyebrow">MANAGEMENT</p><h1>Run the clinic, <em>your way.</em></h1><p className="workspace-page-intro">Services, staff and access in one place.</p></div><div className="header-actions"><button className="button button-secondary" onClick={() => void load()} disabled={loading}>Refresh <span>↻</span></button></div></div>
    {error && <div className="workspace-alert" role="alert"><strong>{error}</strong><button className="ghost-button" onClick={() => void load()}>Try again <span>→</span></button></div>}

    <div className="pipeline-toolbar"><div className="pipeline-tabs" role="tablist">{visibleTabs.map((item) => <button key={item.id} role="tab" aria-selected={tab === item.id} className={tab === item.id ? "active" : ""} onClick={() => setTab(item.id)}>{item.label}</button>)}</div></div>

    {/* ═══ SERVICES TAB ═══ */}
    {tab === "services" && <section className="surface-card">
      <div className="surface-card-heading"><div><p className="eyebrow">SERVICE CATALOG</p><h2>What patients can book.</h2></div>
        <div className="header-actions" style={{ display: "flex", gap: 8 }}>
          {can("service.manage") && <button className="button button-secondary" onClick={() => setImportDrawer(true)}>Import from catalog</button>}
          {can("service.manage") && <button className="button button-primary" onClick={() => { setEditService(null); setServiceDrawer(true); }}>Add service <span>＋</span></button>}
        </div>
      </div>

      <div className="pipeline-toolbar" style={{ marginBottom: 12 }}>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", flex: 1 }}>
          <input type="search" placeholder="Search services…" value={serviceSearch} onChange={(e) => setServiceSearch(e.target.value)} style={{ maxWidth: 240, padding: "6px 12px", border: "1px solid var(--border-subtle, #e5e5e3)", borderRadius: 6, fontSize: "0.85rem", background: "var(--surface-1, #fff)" }} />
          <div className="pipeline-tabs" role="tablist" style={{ fontSize: "0.78rem" }}>
            <button role="tab" aria-selected={serviceFilter === "all"} className={serviceFilter === "all" ? "active" : ""} onClick={() => setServiceFilter("all")}>All ({services.length})</button>
            {categories.map((cat) => <button key={cat} role="tab" aria-selected={serviceFilter === cat} className={serviceFilter === cat ? "active" : ""} onClick={() => setServiceFilter(cat)}>{cat} ({services.filter((s) => (s.category ?? "General") === cat).length})</button>)}
          </div>
        </div>
      </div>

      <div className="invoice-list">
        {!loading && filteredServices.length === 0 && <div className="dashboard-empty"><strong>{serviceSearch || serviceFilter !== "all" ? "No matching services" : "No services yet"}</strong><span>Add one or import from the master catalog.</span></div>}
        {filteredServices.map((item) => <article className="invoice-row" key={item.id}>
          <div className="invoice-mark">{item.name.slice(0, 2).toUpperCase()}</div>
          <div className="invoice-main">
            <h3>{item.name}</h3>
            <p>{item.category ?? "General"} · {item.duration_minutes} min{item.buffer_before_minutes || item.buffer_after_minutes ? ` (${item.buffer_before_minutes}+${item.buffer_after_minutes} buffer)` : ""} · {item.price_mode === "contact" || item.amount_minor == null ? "Contact for price" : money(item.amount_minor, item.currency ?? clinicCurrency)}</p>
            {item.short_description && <small style={{ color: "var(--text-muted, #6b7280)" }}>{item.short_description}</small>}
          </div>
          <div className="invoice-actions">
            <span className={`pipeline-status status-${item.status === "active" ? "paid" : "void"}`}>{item.status}</span>
            <span className={`pipeline-status status-${item.visibility === "public" ? "contacted" : "void"}`} style={{ fontSize: "0.7rem" }}>{item.visibility}</span>
            {can("service.manage") && <>
              <button className="text-control" disabled={busy} onClick={() => { setEditService(item); setServiceDrawer(true); }}>Edit</button>
              <button className="text-control" disabled={busy} onClick={() => duplicateService(item)}>Duplicate</button>
              <button className="text-control" disabled={busy} onClick={() => void run(() => patch(`/api/v1/services/${item.id}`, { expected_version: item.version, visibility: item.visibility === "public" ? "hidden" : "public" }), "Visibility updated.", "The service could not be updated.")}>{item.visibility === "public" ? "Hide" : "Show"}</button>
              <button className="text-control" disabled={busy} onClick={() => void toggleServiceStatus(item)}>{item.status === "active" ? "Deactivate" : "Reactivate"}</button>
            </>}
          </div>
        </article>)}
      </div>
    </section>}

    {/* ═══ STAFF TAB ═══ */}
    {tab === "staff" && <section className="surface-card">
      <div className="surface-card-heading"><div><p className="eyebrow">TEAM</p><h2>Invite, don't share logins.</h2></div>{can("staff.manage") && <button className="button button-primary" onClick={() => setStaffDrawer(true)}>Invite staff <span>＋</span></button>}</div>

      {invitations.filter((i) => i.status === "pending").length > 0 && <div style={{ marginBottom: 16 }}>
        <p className="eyebrow" style={{ margin: "12px 0 6px", fontSize: "0.68rem" }}>PENDING INVITATIONS</p>
        <div className="invoice-list">
          {invitations.filter((i) => i.status === "pending").map((inv) => <article className="invoice-row" key={inv.id}>
            <div className="invoice-mark" style={{ background: "var(--amber-bg, #fffbeb)", color: "var(--amber, #92400e)" }}>✉</div>
            <div className="invoice-main">
              <h3>{inv.email}</h3>
              <small>Invited {new Date(inv.created_at).toLocaleDateString()}</small>
            </div>
            <div className="invoice-actions">
              <span className="pipeline-status status-contacted">Pending</span>
              {can("staff.manage") && <button className="text-control" disabled={busy} onClick={() => void revokeInvitation(inv.id)}>Cancel</button>}
            </div>
          </article>)}
        </div>
      </div>}

      <div className="invoice-list">
        {!loading && staff.length === 0 && <div className="dashboard-empty"><strong>No staff yet</strong><span>Invited team members appear here once they accept.</span></div>}
        {staff.map((item) => <article className="invoice-row" key={item.id}>
          <div className="invoice-mark">{item.display_name.slice(0, 2).toUpperCase()}</div>
          <div className="invoice-main">
            <h3>{item.display_name}</h3>
            <p>{item.normalized_email}</p>
            <small>{item.last_login_at ? `Last sign-in ${new Date(item.last_login_at).toLocaleDateString()}` : "Never signed in"}</small>
          </div>
          <div className="invoice-actions">
            <span className={`pipeline-status status-${item.status === "active" ? "paid" : "void"}`}>{item.status}</span>
            {can("staff.manage") && <>
              <button className="text-control" disabled={busy} onClick={() => void loadStaffDetail(item)}>Manage</button>
              <button className="text-control" disabled={busy} onClick={() => void run(() => post(`/api/v1/staff/users/${item.id}/status`, { expected_version: item.version, status: item.status === "active" ? "suspended" : "active" }), "Staff status updated.", "The status could not be changed.")}>{item.status === "active" ? "Suspend" : "Reactivate"}</button>
            </>}
          </div>
        </article>)}
      </div>
    </section>}

    {/* ═══ ROLES TAB ═══ */}
    {tab === "roles" && <section className="surface-card">
      <div className="surface-card-heading"><div><p className="eyebrow">ACCESS CONTROL</p><h2>What each role can do.</h2></div>
        {can("staff.manage") && <button className="button button-primary" onClick={() => { setEditRole(null); setRoleDrawer(true); }}>Create role <span>＋</span></button>}
      </div>
      <div className="invoice-list">{roles.map((role) => <article className="invoice-row" key={role.id} style={{ cursor: "pointer" }} onClick={() => setRoleDetail(roleDetail?.id === role.id ? null : role)}>
        <div className="invoice-mark">{role.name.slice(0, 2).toUpperCase()}</div>
        <div className="invoice-main">
          <h3>{label(role.name)}{role.is_system ? <span style={{ fontSize: "0.7rem", color: "var(--muted)", marginLeft: 8 }}>System role</span> : <span style={{ fontSize: "0.7rem", color: "var(--leaf)", marginLeft: 8 }}>Custom</span>}</h3>
          <p>{role.permissions.length} permissions</p>
          {roleDetail?.id === role.id && <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px dashed var(--line)" }}>
            <p className="eyebrow" style={{ fontSize: "0.65rem", marginBottom: 8 }}>PERMISSIONS</p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
              {role.permissions.map((p) => <span key={p.code} className="tag-pill" style={{ fontFamily: "'DM Mono', monospace", fontSize: "0.72rem" }}>{p.code}</span>)}
            </div>
            {can("staff.manage") && <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
              <button className="button button-secondary" disabled={busy} onClick={(e) => { e.stopPropagation(); setEditRole(role); setRoleDrawer(true); }}>Edit permissions</button>
              {!role.is_system && <button className="button button-danger" disabled={busy} onClick={(e) => { e.stopPropagation(); void (async () => {
                const ok = await confirm({ message: `Delete the "${label(role.name)}" role? This cannot be undone.`, danger: true, confirmLabel: "Delete role" });
                if (!ok) return;
                void run(
                  () => api(`/api/v1/staff/roles/${role.id}`, { method: "DELETE", headers: writeHeaders() }),
                  "Role deleted.", "The role could not be deleted."
                );
                setRoleDetail(null);
              })(); }}>Delete</button>}
            </div>}
          </div>}
        </div>
      </article>)}</div>
    </section>}

    {/* ═══ MODULES TAB ═══ */}
    {tab === "modules" && <section className="surface-card">
      <div className="surface-card-heading"><div><p className="eyebrow">SPECIALTIES &amp; PLAN</p><h2>Grow without migrating.</h2></div></div>

      {subscription && <div style={{ padding: "16px 20px", marginBottom: 12, background: "var(--surface-2, #f0f0ee)", borderRadius: 8 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
          <div>
            <p className="eyebrow" style={{ fontSize: "0.68rem", marginBottom: 4 }}>CURRENT PLAN</p>
            <strong style={{ fontSize: "1.1rem" }}>{subscription.name}</strong>
            <span className={`pipeline-status ${subscription.status === "active" ? "status-paid" : subscription.status === "cancelled" ? "status-void" : "status-contacted"}`} style={{ marginLeft: 10 }}>{label(subscription.status)}</span>
            {subscription.ends_at && <small style={{ display: "block", marginTop: 4, color: "var(--text-muted, #6b7280)" }}>Ends {new Date(subscription.ends_at).toLocaleDateString()}</small>}
          </div>
          {subscription.status === "active" && can("admin.plan.manage") && <button className="button button-danger" disabled={busy} onClick={() => void (async () => {
            const ok = await confirm({ title: "Cancel subscription", message: "Your clinic will lose access to premium features when the current billing period ends. This cannot be undone from the dashboard — contact support to reactivate.", danger: true, confirmLabel: "Cancel plan" });
            if (!ok) return;
            setBusy(true);
            try {
              await api("/api/v1/governance/subscription", { method: "PUT", headers: writeHeaders(), body: JSON.stringify({ plan_code: subscription.code, status: "cancelled" }) });
              toast.success("Subscription cancelled. Access continues until the end of the current period.");
              await load();
            } catch (reason) { toast.error(errorMessage(reason, "The subscription could not be cancelled.")); }
            finally { setBusy(false); }
          })()}>Cancel plan</button>}
        </div>
      </div>}

      {featureLimits.length > 0 && <div style={{ marginBottom: 20 }}>
        <p className="eyebrow" style={{ fontSize: "0.68rem", margin: "12px 0 8px" }}>PLAN USAGE</p>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 8 }}>
          {featureLimits.map((fl) => {
            const pct = fl.limit_value > 0 ? Math.min(100, Math.round((fl.current_usage / fl.limit_value) * 100)) : 0;
            return <div key={fl.feature} style={{ padding: "10px 14px", background: "var(--surface-2, #f0f0ee)", borderRadius: 8, fontSize: "0.82rem" }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}><strong>{label(fl.feature)}</strong><span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: "0.75rem" }}>{fl.current_usage}/{fl.limit_value}</span></div>
              <div style={{ height: 6, background: "var(--border-subtle, #e5e5e3)", borderRadius: 3, overflow: "hidden" }}>
                <div style={{ height: "100%", width: `${pct}%`, background: pct > 90 ? "var(--red, #b91c1c)" : pct > 70 ? "var(--amber, #92400e)" : "var(--accent, #274c42)", borderRadius: 3, transition: "width 0.3s" }} />
              </div>
            </div>;
          })}
        </div>
      </div>}

      <div className="invoice-list">
        {specialties.map((item) => <article className="invoice-row" key={item.id}>
          <div className="invoice-mark">{item.code.slice(0, 3).toUpperCase()}</div>
          <div className="invoice-main"><h3>{item.name}</h3><p>{item.description}</p></div>
          <div className="invoice-actions">
            {item.enabled
              ? <span className="pipeline-status status-paid">Enabled</span>
              : upgrades.some((r) => r.kind === "specialty" && r.target_code === item.code && r.status === "pending")
                ? <span className="pipeline-status status-contacted">Request pending</span>
                : can("clinic.update") ? <button className="button button-secondary" disabled={busy} onClick={() => requestAccess(item.code)}>Request access</button>
                  : <span className="pipeline-status status-void">Locked</span>}
          </div>
        </article>)}
      </div>

      {upgrades.length > 0 && <>
        <div className="surface-card-heading manage-subhead" style={{ marginTop: 20 }}><div><p className="eyebrow">REQUEST HISTORY</p></div></div>
        <div className="invoice-list">{upgrades.map((item) => <article className="invoice-row" key={item.id}>
          <div className="invoice-mark">↑</div>
          <div className="invoice-main">
            <h3>{label(item.kind)} · {item.target_code}</h3>
            <p>{item.decision_note ?? item.message ?? "Awaiting review"}</p>
            <small>{new Date(item.created_at).toLocaleString()}</small>
          </div>
          <div className="invoice-actions">
            <span className={`pipeline-status status-${item.status === "approved" ? "paid" : item.status === "pending" ? "contacted" : "void"}`}>{item.status}</span>
            {item.status === "pending" && can("clinic.update") && <button className="text-control" disabled={busy} onClick={() => void run(() => post(`/api/v1/upgrade-requests/${item.id}/cancel`), "Request cancelled.", "The request could not be cancelled.")}>Cancel</button>}
          </div>
        </article>)}</div>
      </>}
    </section>}

    {/* ═══ SERVICE DRAWER ═══ */}
    <Drawer open={serviceDrawer} onClose={() => { setServiceDrawer(false); setEditService(null); }} title={editService ? "Edit service" : "Add service"} subtitle="SERVICE CATALOG" width={480} opaque footer={<><button className="button button-secondary" type="button" onClick={() => { setServiceDrawer(false); setEditService(null); }} disabled={busy}>Cancel</button><button className="button button-primary" type="submit" form="service-form" disabled={busy}>{busy ? "Saving…" : editService ? "Update service" : "Save service"} <span>→</span></button></>}>
      <form className="drawer-form" id="service-form" onSubmit={handleServiceSubmit}>
        <label>Service name<input name="name" required maxLength={160} placeholder="e.g. HydraFacial, Teeth Cleaning" defaultValue={editService?.name ?? ""} key={editService?.id ?? "new"} /></label>
        <div className="drawer-form-row drawer-form-row-2">
          <label>Category <span className="field-optional">optional</span>
            <select name="category" defaultValue={editService?.category ?? ""} key={`cat-${editService?.id ?? "new"}`}>
              <option value="">None</option>
              {SERVICE_CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </label>
          <label>Duration (min)<input name="duration" type="number" min={5} max={1440} defaultValue={editService?.duration_minutes ?? 30} required key={`dur-${editService?.id ?? "new"}`} /></label>
        </div>
        <label>Short description <span className="field-optional">optional</span><input name="short_description" maxLength={500} placeholder="Brief description for listings" defaultValue={editService?.short_description ?? ""} key={`desc-${editService?.id ?? "new"}`} /></label>
        <p className="drawer-form-section-label">SCHEDULING</p>
        <div className="drawer-form-row drawer-form-row-2">
          <label>Buffer before (min)<input name="buffer_before" type="number" min={0} max={240} defaultValue={editService?.buffer_before_minutes ?? 0} key={`bb-${editService?.id ?? "new"}`} /></label>
          <label>Buffer after (min)<input name="buffer_after" type="number" min={0} max={240} defaultValue={editService?.buffer_after_minutes ?? 0} key={`ba-${editService?.id ?? "new"}`} /></label>
        </div>
        <p className="drawer-form-section-label">PRICING</p>
        <div className="drawer-form-row drawer-form-row-2">
          <label>Pricing model<select name="price_mode" defaultValue={editService?.price_mode ?? "exact"} key={`pm-${editService?.id ?? "new"}`}><option value="exact">Exact price</option><option value="starting_at">Starting at</option><option value="range">Range</option><option value="contact">Contact for price</option></select></label>
          <label>Price ({clinicCurrency})<input name="amount" type="number" min={0} step="0.01" defaultValue={editService?.amount_minor != null ? editService.amount_minor / 100 : 0} key={`amt-${editService?.id ?? "new"}`} /></label>
        </div>
        <p className="drawer-form-section-label">BOOKING &amp; VISIBILITY</p>
        <div className="drawer-form-row drawer-form-row-2">
          <label>Approval<select name="approval_mode" defaultValue={editService?.approval_mode ?? "staff_approval"} key={`ap-${editService?.id ?? "new"}`}><option value="instant">Instant booking</option><option value="staff_approval">Staff approval</option></select></label>
          <label>Website visibility<select name="visibility" defaultValue={editService?.visibility ?? "public"} key={`vis-${editService?.id ?? "new"}`}><option value="public">Visible</option><option value="hidden">Hidden</option></select></label>
        </div>
      </form>
    </Drawer>

    {/* ═══ IMPORT DRAWER ═══ */}
    <Drawer open={importDrawer} onClose={() => setImportDrawer(false)} title="Import from master catalog" subtitle="SERVICE TEMPLATES" opaque>
      <div className="drawer-form">
        {templates.length === 0 && <p className="drawer-note">No templates available in the master catalog, or you&#39;ve imported them all.</p>}
        {templates.map((t) => <article className="invoice-row" key={t.id} style={{ cursor: "pointer" }} onClick={() => importTemplate(t)}>
          <div className="invoice-mark">{t.name.slice(0, 2).toUpperCase()}</div>
          <div className="invoice-main">
            <h3>{t.name}</h3>
            <p>{t.category ?? "General"}{t.specialty_code ? ` · ${t.specialty_code}` : ""} · {t.duration_minutes} min{t.amount_minor != null ? ` · ${money(t.amount_minor, t.currency ?? clinicCurrency)}` : ""}</p>
          </div>
          <div className="invoice-actions"><button className="button button-secondary" disabled={busy}>Import</button></div>
        </article>)}
      </div>
    </Drawer>

    {/* ═══ STAFF INVITE DRAWER ═══ */}
    <Drawer open={staffDrawer} onClose={() => setStaffDrawer(false)} title="Invite staff member" subtitle="NEW INVITATION" opaque footer={<><button className="button button-secondary" type="button" onClick={() => setStaffDrawer(false)} disabled={busy}>Cancel</button><button className="button button-primary" type="submit" form="invite-form" disabled={busy}>{busy ? "Sending…" : "Send invitation"} <span>→</span></button></>}>
      <form className="drawer-form" id="invite-form" onSubmit={handleInvite}>
        <label>Email address<input name="email" type="email" required placeholder="doctor@clinic.com" /></label>
        <div style={{ padding: "16px", background: "var(--cream)", borderRadius: 8, marginTop: 4 }}>
          <p className="drawer-note" style={{ margin: 0 }}>An invitation link will be generated and copied to your clipboard. Roles and branch scopes can be assigned after the staff member accepts.</p>
        </div>
      </form>
    </Drawer>

    {/* ═══ ROLE DRAWER ═══ */}
    <Drawer open={roleDrawer} onClose={() => { setRoleDrawer(false); setEditRole(null); }} title={editRole ? `Edit ${label(editRole.name)}` : "Create role"} subtitle="ACCESS CONTROL" opaque footer={<><button className="button button-secondary" type="button" onClick={() => { setRoleDrawer(false); setEditRole(null); }} disabled={busy}>Cancel</button><button className="button button-primary" type="submit" form="role-form" disabled={busy}>{busy ? "Saving…" : editRole ? "Update role" : "Create role"} <span>→</span></button></>}>
      <RoleEditor
        role={editRole}
        allPermissions={allPermissions}
        onSave={(name, perms) => {
          if (editRole) {
            const body: Record<string, unknown> = { permissions: perms };
            if (!editRole.is_system) body.name = name;
            void run(
              () => patch(`/api/v1/staff/roles/${editRole.id}`, body),
              "Role updated.", "The role could not be updated."
            ).then(() => { setRoleDrawer(false); setEditRole(null); setRoleDetail(null); });
          } else {
            void run(
              () => post("/api/v1/staff/roles", { name, permissions: perms }),
              "Role created.", "The role could not be created."
            ).then(() => { setRoleDrawer(false); setEditRole(null); });
          }
        }}
      />
    </Drawer>

    {/* ═══ STAFF DETAIL DRAWER ═══ */}
    <Drawer open={!!staffDetail} onClose={() => setStaffDetail(null)} title={staffDetail ? `Manage ${staffDetail.display_name}` : "Staff detail"} subtitle="TEAM MEMBER" opaque footer={can("staff.manage") ? <><button className="button button-secondary" type="button" onClick={() => setStaffDetail(null)}>Close</button><button className="button button-secondary" disabled={busy} onClick={() => { if (staffDetail) void resetStaffPassword(staffDetail); }}>Reset password</button></> : undefined}>
      {staffDetail && <div className="drawer-form staff-info">
        <div>
          <p className="drawer-note">{staffDetail.normalized_email}</p>
          <span className={`pipeline-status status-${staffDetail.status === "active" ? "paid" : "void"}`}>{staffDetail.status}</span>
        </div>

        <div>
          <p className="section-label">ASSIGNED ROLES</p>
          {currentUserId && staffDetail.id === currentUserId && <p className="drawer-note">You cannot modify your own roles.</p>}
          {(staffDetail.roles ?? []).length === 0
            ? <p className="drawer-note">No roles assigned</p>
            : <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {(staffDetail.roles ?? []).map((r) => <span key={r.id} className="tag-pill">
                {label(r.name)}
                {can("staff.manage") && staffDetail.id !== currentUserId && <button className="tag-pill-remove" disabled={busy} onClick={(e) => { e.stopPropagation(); void removeRole(staffDetail.id, r.id); }} title="Remove role">×</button>}
              </span>)}
            </div>}
          {can("staff.manage") && staffDetail.id !== currentUserId && <div style={{ marginTop: 8 }}>
            <select className="staff-scope-select" onChange={(e) => { if (e.target.value) { void assignRole(staffDetail.id, e.target.value); e.target.value = ""; } }}>
              <option value="">+ Add role…</option>
              {roles.filter((r) => !(staffDetail.roles ?? []).some((ur) => ur.id === r.id)).map((r) => <option key={r.id} value={r.id}>{label(r.name)}</option>)}
            </select>
          </div>}
        </div>

        <div>
          <p className="section-label">BRANCH SCOPES</p>
          <p className="drawer-note">Restrict this user to specific branches. No scopes = access to all branches.</p>
          {(staffDetail.branch_scopes ?? []).length === 0
            ? <p className="drawer-note">All branches (no restrictions)</p>
            : <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {(staffDetail.branch_scopes ?? []).map((b) => <span key={b.id} className="tag-pill">
                {b.name}
                {can("staff.manage") && <button className="tag-pill-remove" disabled={busy} onClick={(e) => { e.stopPropagation(); void removeBranchScope(staffDetail.id, b.id); }} title="Remove scope">×</button>}
              </span>)}
            </div>}
          {can("staff.manage") && <div style={{ marginTop: 8 }}>
            <select className="staff-scope-select" onChange={(e) => { if (e.target.value) { void assignBranchScope(staffDetail.id, e.target.value); e.target.value = ""; } }}>
              <option value="">+ Add branch scope…</option>
              {branches.filter((b) => !(staffDetail.branch_scopes ?? []).some((bs) => bs.id === b.id)).map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
            </select>
          </div>}
        </div>
      </div>}
    </Drawer>
  </main>;
}

function RoleEditor({ role, allPermissions, onSave }: {
  role: Role | null;
  allPermissions: { code: string; description: string }[];
  onSave: (name: string, permissions: string[]) => void;
}) {
  const [name, setName] = useState(role?.name ?? "");
  const [selected, setSelected] = useState<Set<string>>(new Set(role?.permissions.map((p) => p.code) ?? []));
  const [search, setSearch] = useState("");

  const groups = useMemo(() => {
    const map = new Map<string, { code: string; description: string }[]>();
    for (const p of allPermissions) {
      const group = p.code.split(".")[0];
      if (!map.has(group)) map.set(group, []);
      map.get(group)!.push(p);
    }
    return Array.from(map.entries()).sort((a, b) => a[0].localeCompare(b[0]));
  }, [allPermissions]);

  const toggle = (code: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code); else next.add(code);
      return next;
    });
  };

  const toggleGroup = (codes: string[]) => {
    const allOn = codes.every((c) => selected.has(c));
    setSelected((prev) => {
      const next = new Set(prev);
      for (const c of codes) { if (allOn) next.delete(c); else next.add(c); }
      return next;
    });
  };

  const filtered = search
    ? groups.map(([g, perms]) => [g, perms.filter((p) => p.code.includes(search.toLowerCase()) || p.description.toLowerCase().includes(search.toLowerCase()))] as [string, typeof perms]).filter(([, p]) => p.length > 0)
    : groups;

  return <form className="drawer-form" id="role-form" onSubmit={(e) => { e.preventDefault(); onSave(name.trim(), Array.from(selected).sort()); }}>
    {!(role?.is_system) && <label>Role name<input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Lab Technician" required /></label>}
    {role?.is_system && <div style={{ padding: "12px 16px", background: "var(--cream)", borderRadius: 8 }}><p className="drawer-note" style={{ margin: 0 }}>System role — name cannot be changed, but you can edit permissions.</p></div>}
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <p className="drawer-form-section-label" style={{ margin: 0, padding: 0, border: "none" }}>PERMISSIONS ({selected.size}/{allPermissions.length})</p>
        <div style={{ display: "flex", gap: 8 }}>
          <button type="button" className="ghost-button" style={{ fontSize: "0.72rem" }} onClick={() => setSelected(new Set(allPermissions.map((p) => p.code)))}>Select all</button>
          <button type="button" className="ghost-button" style={{ fontSize: "0.72rem" }} onClick={() => setSelected(new Set())}>Clear all</button>
        </div>
      </div>
      <input type="search" placeholder="Filter permissions…" value={search} onChange={(e) => setSearch(e.target.value)} style={{ marginBottom: 10 }} />
      <div className="role-permissions">
        {filtered.map(([group, perms]) => (
          <div key={group} style={{ borderBottom: "1px solid var(--line)" }}>
            <div className="perm-group-header" onClick={() => toggleGroup(perms.map((p) => p.code))}>
              <input type="checkbox" checked={perms.every((p) => selected.has(p.code))} readOnly />
              <strong>{group}</strong>
              <span>({perms.filter((p) => selected.has(p.code)).length}/{perms.length})</span>
            </div>
            {perms.map((p) => (
              <label key={p.code} className="perm-item">
                <input type="checkbox" checked={selected.has(p.code)} onChange={() => toggle(p.code)} />
                <span className="perm-code">{p.code}</span>
                <span className="perm-desc">{p.description}</span>
              </label>
            ))}
          </div>
        ))}
      </div>
    </div>
  </form>;
}
