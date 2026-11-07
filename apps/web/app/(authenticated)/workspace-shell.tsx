"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, post, redirectToLogin } from "./_lib/client";
import { invalidateCache } from "./_lib/session-cache";
import type { SessionInfo } from "./_lib/contracts";
type NavItem = { href: string; label: string; icon: string; permission: string; adminOnly?: boolean };
type NavGroup = { key: string; label: string; items: NavItem[] };

const navGroups: NavGroup[] = [
  { key: "home", label: "", items: [
    { href: "/dashboard", label: "Overview", icon: "◈", permission: "appointment.read" },
  ]},
  { key: "crm", label: "CRM", items: [
    { href: "/schedule", label: "Schedule", icon: "◷", permission: "appointment.read" },
    { href: "/patients", label: "Patients", icon: "○", permission: "patient.read" },
    { href: "/leads", label: "Leads", icon: "↳", permission: "lead.read" },
    { href: "/queue", label: "Queue", icon: "▣", permission: "queue.read" },
    { href: "/operations", label: "Follow-ups", icon: "↗", permission: "followup.read" },
  ]},
  { key: "clinical", label: "CLINICAL", items: [
    { href: "/doctors", label: "Doctors", icon: "⚕", permission: "doctor.read" },
    { href: "/encounters", label: "Encounters", icon: "✍", permission: "clinical.read" },
    { href: "/branches", label: "Branches", icon: "⌂", permission: "branch.read" },
    { href: "/services", label: "Services", icon: "▦", permission: "service.read" },
    { href: "/clinical", label: "Clinical", icon: "✚", permission: "clinical.read" },
  ]},
  { key: "business", label: "BUSINESS", items: [
    { href: "/billing", label: "Billing", icon: "₿", permission: "billing.read" },
    { href: "/finance", label: "Finance", icon: "∑", permission: "billing.read" },
    { href: "/packages", label: "Packages", icon: "❑", permission: "package.read" },
    { href: "/reports", label: "Reports", icon: "▤", permission: "report.read" },
    { href: "/inventory", label: "Inventory", icon: "◌", permission: "inventory.read" },
  ]},
  { key: "website", label: "WEBSITE", items: [
    { href: "/website", label: "Website", icon: "✦", permission: "website.read" },
    { href: "/content", label: "Content", icon: "✎", permission: "website.read" },
    { href: "/domains", label: "Domains", icon: "◎", permission: "website.read" },
    { href: "/media", label: "Media", icon: "▣", permission: "website.read" },
    { href: "/analytics", label: "Analytics", icon: "◈", permission: "report.read" },
  ]},
  { key: "manage", label: "MANAGEMENT", items: [
    { href: "/manage", label: "Manage", icon: "⚙", permission: "clinic.update" },
    { href: "/notifications", label: "Alerts", icon: "◔", permission: "notification.read" },
    { href: "/security", label: "Security", icon: "⚿", permission: "" },
    { href: "/privacy", label: "Privacy", icon: "◇", permission: "patient.read" },
    { href: "/admin", label: "Platform", icon: "◆", permission: "audit.read", adminOnly: true },
  ]},
];

const greeting = () => { const h = new Date().getHours(); return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening"; };

export default function WorkspaceShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [connectionIssue, setConnectionIssue] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  useEffect(() => {
    let mounted = true;
    void api<SessionInfo>("/api/v1/auth/me")
      .then((data) => { if (mounted) setSession(data); })
      .catch(() => { if (mounted) setConnectionIssue(true); });
    return () => { mounted = false; };
  }, []);

  const permissions = session?.permissions ?? [];

  const isAdmin = session?.is_platform_admin === true;

  const visibleGroups = useMemo(() => {
    return navGroups.map((group) => ({
      ...group,
      items: group.items.filter((item) => {
        if (!session) return true;
        if (item.adminOnly && !isAdmin) return false;
        if (isAdmin) return true;
        return !item.permission || permissions.includes(item.permission);
      }),
    })).filter((group) => group.items.length > 0);
  }, [permissions, session, isAdmin]);

  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const toggleGroup = useCallback((key: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  }, []);

  const activeGroup = useMemo(() => {
    for (const group of navGroups) {
      if (group.items.some((item) => pathname === item.href || pathname.startsWith(`${item.href}/`))) return group.key;
    }
    return null;
  }, [pathname]);

  const initials = (session?.display_name ?? "Care team").split(/\s+/).map((part) => part[0]).join("").slice(0, 2).toUpperCase();
  const [accountOpen, setAccountOpen] = useState(false);
  const accountRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!accountOpen) return;
    function close(e: MouseEvent) { if (accountRef.current && !accountRef.current.contains(e.target as Node)) setAccountOpen(false); }
    function escape(e: KeyboardEvent) { if (e.key === "Escape") setAccountOpen(false); }
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", escape); };
  }, [accountOpen]);

  useEffect(() => { setMobileNavOpen(false); }, [pathname]);

  const signOut = useCallback(async () => {
    invalidateCache();
    try { await post("/api/v1/auth/logout"); } catch { /* continue */ }
    redirectToLogin();
  }, []);

  return <div className="workspace-layout">
    <aside className={`workspace-sidebar ${mobileNavOpen ? "sidebar-open" : ""}`} aria-label="Authenticated workspace navigation">
      <Link className="workspace-brand" href="/">care<span>/</span>fully</Link>
      <nav className="workspace-nav">
        {visibleGroups.map((group) => {
          const isCollapsed = collapsed.has(group.key);
          const hasLabel = group.label.length > 0;
          const isActive = activeGroup === group.key;
          return (
            <div key={group.key} className={`nav-group ${isActive ? "nav-group-active" : ""}`}>
              {hasLabel && (
                <button
                  className="nav-group-toggle"
                  type="button"
                  onClick={() => toggleGroup(group.key)}
                  aria-expanded={!isCollapsed}
                >
                  <span className="nav-group-label">{group.label}</span>
                  <span className={`nav-group-chevron ${isCollapsed ? "collapsed" : ""}`} aria-hidden="true">›</span>
                </button>
              )}
              {(!hasLabel || !isCollapsed) && group.items.map((item) => (
                <Link
                  className={`workspace-nav-link ${pathname === item.href || pathname.startsWith(`${item.href}/`) ? "active" : ""}`}
                  href={item.href}
                  key={item.href}
                  aria-current={pathname === item.href ? "page" : undefined}
                >
                  <span aria-hidden="true">{item.icon}</span>{item.label}
                </Link>
              ))}
            </div>
          );
        })}
      </nav>
      <div className="workspace-sidebar-foot"><span className="workspace-status-dot" />Live clinic data</div>
    </aside>
    {mobileNavOpen && <div className="sidebar-scrim" onClick={() => setMobileNavOpen(false)} />}
    <div className="workspace-stage">
      <header className="workspace-topbar">
        <div>
          <button className="mobile-nav-toggle" type="button" aria-label="Toggle navigation" onClick={() => setMobileNavOpen((v) => !v)}>☰</button>
          <p className="workspace-context">{session ? "Signed in" : "Checking access…"}</p>
          <span className="workspace-greeting">{greeting()}, <em>{session?.display_name ?? "team"}.</em></span>
        </div>
        <div className="workspace-top-actions">
          <div ref={accountRef} style={{ position: "relative" }}>
            <button className="workspace-avatar" type="button" aria-label="Open account menu" aria-expanded={accountOpen} onClick={() => setAccountOpen((v) => !v)}>{initials}</button>
            {accountOpen && <div className="account-menu" role="menu">
              <div className="account-menu-header">
                <strong>{session?.display_name ?? "Team member"}</strong>
                {session?.email && <small>{session.email}</small>}
                {session?.is_platform_admin && <span className="account-menu-badge">Platform admin</span>}
              </div>
              <hr />
              <Link className="account-menu-item" href="/security" role="menuitem" onClick={() => setAccountOpen(false)}>⚿ Security</Link>
              <Link className="account-menu-item" href="/privacy" role="menuitem" onClick={() => setAccountOpen(false)}>◇ Privacy</Link>
              <hr />
              <button className="account-menu-item account-menu-signout" role="menuitem" onClick={signOut}>Sign out</button>
            </div>}
          </div>
        </div>
      </header>
      {connectionIssue && <div className="workspace-connection-alert" role="alert" style={{ display: "flex", alignItems: "center", gap: 12, justifyContent: "center" }}>The API server could not be reached. Check your internet connection or try again. <button className="button button-secondary" type="button" style={{ fontSize: 11, padding: "4px 12px" }} onClick={() => window.location.reload()}>Reload</button> <button className="ghost-button" type="button" style={{ fontSize: 11, padding: "4px 8px" }} onClick={() => redirectToLogin()}>Sign in</button></div>}
      <div className="workspace-body">{children}</div>
    </div>
  </div>;
}
