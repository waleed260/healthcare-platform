"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

type FollowUp = { id: string; reason: string; due_at: string; priority: string; status: string; version: number };
type Notification = { id: string; kind: string; title: string; body: string; read_at: string | null; created_at: string };

function csrf(): string {
  return document.cookie.split("; ").find((item) => item.startsWith("csrf_token="))?.split("=")[1] ?? "";
}

function message(response: Response, payload: unknown): string {
  if (payload && typeof payload === "object" && "error" in payload) {
    const value = (payload as { error?: { message?: string } }).error?.message;
    if (value) return value;
  }
  return response.status === 401 ? "Your clinic session has expired. Sign in again." : "The operations workspace could not be loaded.";
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

export default function OperationsPage() {
  const [followUps, setFollowUps] = useState<FollowUp[]>([]);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [nextFollowUp, setNextFollowUp] = useState<string | null>(null);
  const [nextNotification, setNextNotification] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshedAt, setRefreshedAt] = useState<Date | null>(null);

  const load = useCallback(async (append = false) => {
    setLoading(true);
    setError(null);
    try {
      const followCursor = append ? nextFollowUp : null;
      const notificationCursor = append ? nextNotification : null;
      const followUrl = `/api/v1/operations/follow-ups?limit=25${followCursor ? `&cursor=${encodeURIComponent(followCursor)}` : ""}`;
      const notificationUrl = `/api/v1/operations/notifications?limit=25${notificationCursor ? `&cursor=${encodeURIComponent(notificationCursor)}` : ""}`;
      const [followResponse, notificationResponse] = await Promise.all([
        fetch(followUrl, { credentials: "include", cache: "no-store" }),
        fetch(notificationUrl, { credentials: "include", cache: "no-store" }),
      ]);
      const followPayload = await followResponse.json();
      const notificationPayload = await notificationResponse.json();
      if (!followResponse.ok) throw new Error(message(followResponse, followPayload));
      if (!notificationResponse.ok) throw new Error(message(notificationResponse, notificationPayload));
      setFollowUps((current) => append ? [...current, ...(followPayload.data ?? [])] : (followPayload.data ?? []));
      setNotifications((current) => append ? [...current, ...(notificationPayload.data ?? [])] : (notificationPayload.data ?? []));
      setNextFollowUp(followPayload.meta?.next_cursor ?? null);
      setNextNotification(notificationPayload.meta?.next_cursor ?? null);
      setRefreshedAt(new Date());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The operations workspace could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [nextFollowUp, nextNotification]);

  useEffect(() => { void load(); }, [load]);

  async function complete(item: FollowUp) {
    setWorking(item.id);
    setError(null);
    try {
      const response = await fetch(`/api/v1/operations/follow-ups/${item.id}/complete`, {
        method: "POST", credentials: "include", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf() },
        body: JSON.stringify({ expected_version: item.version }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(message(response, payload));
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The follow-up could not be completed.");
    } finally {
      setWorking(null);
    }
  }

  async function markRead(item: Notification) {
    if (item.read_at) return;
    setWorking(item.id);
    try {
      const response = await fetch("/api/v1/operations/notifications/read", {
        method: "POST", credentials: "include", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf() },
        body: JSON.stringify({ notification_ids: [item.id] }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(message(response, payload));
      setNotifications((current) => current.map((entry) => entry.id === item.id ? { ...entry, read_at: new Date().toISOString() } : entry));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The notification could not be marked read.");
    } finally {
      setWorking(null);
    }
  }

  return <main className="dashboard-page">
    <header className="dash-header shell"><Link className="wordmark" href="/">care<span>/</span>fully</Link><div className="clinic-chip" aria-label="Clinic operations session"><span className="clinic-avatar">OP</span><span>Operations workspace</span></div></header>
    <div className="dashboard shell">
      <aside className="sidebar"><p className="eyebrow">WORKSPACE</p><nav aria-label="Workspace navigation"><Link className="side-link" href="/dashboard">◈ <span>Overview</span></Link><Link className="side-link" href="/schedule">◷ <span>Schedule</span></Link><Link className="side-link" href="/patients">○ <span>Patients</span></Link><Link className="side-link" href="/queue">▣ <span>Queue</span></Link><Link className="side-link active" href="/operations" aria-current="page">↗ <span>Operations</span></Link><Link className="side-link" href="/website">✦ <span>Website</span></Link></nav></aside>
      <section className="dash-content operations-content" aria-busy={loading}>
        <div className="dash-topline"><div><p className="eyebrow">FOLLOW-UPS · NOTIFICATIONS</p><h1>Keep care <em>moving.</em></h1></div><button className="button button-primary" type="button" onClick={() => void load()} disabled={loading}>Refresh <span>↻</span></button></div>
        <p className="queue-intro">A focused, permission-scoped handoff for tasks that need attention. Patient details stay in the protected patient workspace.</p>
        {error && <div className="workspace-alert" role="alert"><strong>{error}</strong><button className="ghost-button" type="button" onClick={() => void load()}>Try again <span>→</span></button></div>}
        <div className="operations-grid">
          <section className="detail-card operations-card" aria-labelledby="follow-up-heading"><div className="card-heading"><div><p className="eyebrow">ACTION QUEUE</p><h2 id="follow-up-heading">Follow-ups</h2></div><span className="directory-count">{followUps.length} shown</span></div>{loading && followUps.length === 0 && <div className="dashboard-empty" role="status"><strong>Loading follow-ups</strong><span>Checking your scoped task list…</span></div>}{!loading && !error && followUps.length === 0 && <div className="dashboard-empty"><strong>No follow-ups need attention</strong><span>New tasks will appear here when they are assigned.</span></div>}{followUps.length > 0 && <div className="operations-list">{followUps.map((item) => <article className="operations-row" key={item.id}><div><strong>{item.reason}</strong><small>Due {formatDate(item.due_at)} · {item.priority} priority · {item.status}</small></div><button className="button button-secondary" type="button" onClick={() => void complete(item)} disabled={working === item.id || item.status === "completed"}>{working === item.id ? "Saving…" : "Complete"}</button></article>)}</div>}{nextFollowUp && <button className="button button-secondary" type="button" onClick={() => void load(true)} disabled={loading}>Load more follow-ups <span>↓</span></button>}</section>
          <section className="detail-card operations-card" aria-labelledby="notification-heading"><div className="card-heading"><div><p className="eyebrow">INBOX</p><h2 id="notification-heading">Notifications</h2></div><span className="directory-count">{notifications.filter((item) => !item.read_at).length} unread</span></div>{loading && notifications.length === 0 && <div className="dashboard-empty" role="status"><strong>Loading notifications</strong><span>Checking your private inbox…</span></div>}{!loading && !error && notifications.length === 0 && <div className="dashboard-empty"><strong>Your inbox is clear</strong><span>Operational alerts will appear here.</span></div>}{notifications.length > 0 && <div className="operations-list">{notifications.map((item) => <article className={item.read_at ? "operations-row notification-read" : "operations-row notification-unread"} key={item.id}><div><strong>{item.title}</strong><small>{item.body} · {formatDate(item.created_at)}</small></div>{!item.read_at && <button className="ghost-button" type="button" onClick={() => void markRead(item)} disabled={working === item.id}>Mark read <span>✓</span></button>}</article>)}</div>}{nextNotification && <button className="button button-secondary" type="button" onClick={() => void load(true)} disabled={loading}>Load more notifications <span>↓</span></button>}</section>
        </div>
        {refreshedAt && <p className="stale-note">Updated {refreshedAt.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })} · refresh if the clinic day has changed.</p>}
      </section>
    </div>
  </main>;
}
