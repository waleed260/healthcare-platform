"use client";

import { useCallback, useEffect, useState } from "react";
import { api, errorMessage, label, post } from "../_lib/client";

type Notification = { id: string; kind: string; title: string; body: string; read_at: string | null; created_at: string };

export default function NotificationsPage() {
  const [items, setItems] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [onlyUnread, setOnlyUnread] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setItems(await api<Notification[]>("/api/v1/operations/notifications?limit=100") ?? []);
    } catch (reason) {
      setError(errorMessage(reason, "Notifications could not be loaded."));
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const markRead = async (ids: string[]) => {
    if (ids.length === 0) return;
    try {
      await post("/api/v1/operations/notifications/read", { notification_ids: ids.slice(0, 100) });
      await load();
    } catch (reason) {
      setError(errorMessage(reason, "Could not mark notifications as read."));
    }
  };

  const unread = items.filter((item) => !item.read_at);
  const shown = onlyUnread ? unread : items;

  return <main className="workspace-page">
    <div className="workspace-page-header"><div><p className="eyebrow">HOME · WHAT NEEDS YOU</p><h1>Only the <em>relevant</em> alerts.</h1><p className="workspace-page-intro">Reminders, follow-ups, payments and platform notices addressed to your role.</p></div><div className="header-actions"><button className="button button-secondary" onClick={() => setOnlyUnread((value) => !value)}>{onlyUnread ? "Show all" : `Unread only (${unread.length})`}</button><button className="button button-primary" disabled={unread.length === 0} onClick={() => void markRead(unread.map((item) => item.id))}>Mark all read <span>✓</span></button></div></div>
    {error && <div className="workspace-alert" role="alert"><strong>{error}</strong><button className="ghost-button" onClick={() => void load()}>Try again <span>→</span></button></div>}
    <section className="surface-card"><div className="invoice-list">
      {loading && <div className="dashboard-empty" role="status"><strong>Loading notifications</strong></div>}
      {!loading && shown.length === 0 && <div className="dashboard-empty"><strong>You’re all caught up</strong><span>New alerts will appear here.</span></div>}
      {shown.map((item) => <article className="invoice-row" key={item.id}><div className="invoice-mark">{item.read_at ? "•" : "!"}</div><div className="invoice-main"><h3>{item.title}</h3><p>{item.body}</p><small>{label(item.kind)} · {new Date(item.created_at).toLocaleString()}</small></div><div className="invoice-actions">{!item.read_at && <button className="text-control" onClick={() => void markRead([item.id])}>Mark read</button>}</div></article>)}
    </div></section>
  </main>;
}
