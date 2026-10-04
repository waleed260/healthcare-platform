"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode, useEffect, useMemo, useState } from "react";

type Session = { display_name?: string; permissions?: string[]; clinic_id?: string | null; is_platform_admin?: boolean };
type Notification = { id: string; read_at: string | null };
type NavItem = { href: string; label: string; icon: string; permission: string };

const navItems: NavItem[] = [
  { href: "/dashboard", label: "Overview", icon: "◈", permission: "appointment.read" },
  { href: "/schedule", label: "Schedule", icon: "◷", permission: "appointment.read" },
  { href: "/patients", label: "Patients", icon: "○", permission: "patient.read" },
  { href: "/leads", label: "Leads", icon: "↳", permission: "lead.read" },
  { href: "/clinical", label: "Clinical", icon: "✚", permission: "clinical.read" },
  { href: "/queue", label: "Queue", icon: "▣", permission: "queue.read" },
  { href: "/billing", label: "Billing", icon: "₿", permission: "billing.read" },
  { href: "/finance", label: "Finance", icon: "∑", permission: "billing.read" },
  { href: "/reports", label: "Reports", icon: "▤", permission: "report.read" },
  { href: "/inventory", label: "Inventory", icon: "◌", permission: "inventory.read" },
  { href: "/operations", label: "Follow-ups", icon: "↗", permission: "followup.read" },
  { href: "/website", label: "Website", icon: "✦", permission: "website.read" },
  { href: "/content", label: "Content", icon: "✎", permission: "website.read" },
  { href: "/manage", label: "Manage", icon: "⚙", permission: "clinic.update" },
  { href: "/notifications", label: "Alerts", icon: "◔", permission: "notification.read" },
  { href: "/security", label: "Security", icon: "⚿", permission: "" },
  { href: "/privacy", label: "Privacy", icon: "◇", permission: "patient.read" },
  { href: "/admin", label: "Platform", icon: "◆", permission: "audit.read" },
];

const greeting = () => { const h = new Date().getHours(); return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening"; };

async function readJson<T>(url: string): Promise<T | null> {
  try {
    const response = await fetch(url, { credentials: "include", cache: "no-store" });
    if (!response.ok) return null;
    const payload = await response.json() as { data?: T };
    return payload.data ?? null;
  } catch {
    return null;
  }
}

export default function WorkspaceShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [session, setSession] = useState<Session | null>(null);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [connectionIssue, setConnectionIssue] = useState(false);

  useEffect(() => {
    let mounted = true;
    void readJson<Session>("/api/v1/auth/me").then(async (nextSession) => {
      if (!mounted) return;
      if (!nextSession) {
        setConnectionIssue(true);
        return;
      }
      setSession(nextSession);
      // Platform administrators have no clinic context, so there is no clinic inbox to poll.
      if (!nextSession.clinic_id || nextSession.is_platform_admin) return;
      const nextNotifications = await readJson<Notification[]>("/api/v1/operations/notifications?limit=25");
      if (mounted) setNotifications(nextNotifications ?? []);
    });
    return () => { mounted = false; };
  }, []);

  const permissions = session?.permissions ?? [];
  const visibleItems = useMemo(() => navItems.filter((item) => !session || !item.permission || permissions.includes(item.permission)), [permissions, session]);
  const unreadCount = notifications.filter((item) => !item.read_at).length;
  const initials = (session?.display_name ?? "Care team").split(/\s+/).map((part) => part[0]).join("").slice(0, 2).toUpperCase();

  return <div className="workspace-layout">
    <aside className="workspace-sidebar" aria-label="Authenticated workspace navigation">
      <Link className="workspace-brand" href="/">care<span>/</span>fully</Link>
      <p className="workspace-label">WORKSPACE</p>
      <nav>{visibleItems.map((item) => <Link className={`workspace-nav-link ${pathname === item.href || pathname.startsWith(`${item.href}/`) ? "active" : ""}`} href={item.href} key={item.href} aria-current={pathname === item.href ? "page" : undefined}><span aria-hidden="true">{item.icon}</span>{item.label}</Link>)}</nav>
      <div className="workspace-sidebar-foot"><span className="workspace-status-dot" />Live clinic data</div>
    </aside>
    <div className="workspace-stage">
      <header className="workspace-topbar"><div><p className="workspace-context">{session ? "Signed in" : "Checking access…"}</p><span className="workspace-greeting">{greeting()}, <em>{session?.display_name ?? "team"}.</em></span></div><div className="workspace-top-actions"><Link className="workspace-notifications" href="/notifications" aria-label={`${unreadCount} unread notifications`}><span aria-hidden="true">◌</span>{unreadCount > 0 && <b>{unreadCount}</b>}</Link><button className="workspace-avatar" type="button" aria-label="Open account menu">{initials}</button></div></header>
      {connectionIssue && <div className="workspace-connection-alert" role="status">Your workspace connection could not be checked. Protected pages will explain how to retry.</div>}
      <div className="workspace-body">{children}</div>
    </div>
  </div>;
}
