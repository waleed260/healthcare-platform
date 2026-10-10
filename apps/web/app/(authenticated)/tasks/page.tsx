"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import anime from "animejs";
import { api, apiPage, errorMessage, writeHeaders } from "../_lib/client";
import { useToast } from "../_lib/toast";
import { useConfirm } from "../_lib/confirm";

type Task = { id: string; title: string; description: string | null; task_type: string; priority: string; status: string; assignee_user_id: string | null; assignee_name: string | null; patient_id: string | null; patient_name: string | null; lead_id: string | null; appointment_id: string | null; due_at: string | null; completed_at: string | null; created_at: string; version: number };
type StaffUser = { user_id: string; display_name: string };
type Session = { permissions?: string[]; user_id?: string };

const taskTypes = ["general", "follow_up", "callback", "review", "billing", "clinical", "admin"] as const;
const priorities = ["low", "normal", "high", "urgent"] as const;
const statusLabel = (v: string) => v.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
const formatDate = (v: string) => new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(v));
const formatDateTime = (v: string) => new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(v));

export default function TasksPage() {
  const toast = useToast();
  const confirm = useConfirm();

  const [tasks, setTasks] = useState<Task[]>([]);
  const [staffUsers, setStaffUsers] = useState<StaffUser[]>([]);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [userId, setUserId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>("open");
  const [showForm, setShowForm] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [taskType, setTaskType] = useState("general");
  const [priority, setPriority] = useState("normal");
  const [assigneeId, setAssigneeId] = useState("");
  const [dueAt, setDueAt] = useState("");

  const loadTasks = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ limit: "100" });
      if (filter !== "all") params.set("status", filter);
      const [session, page, staffRows] = await Promise.all([
        api<Session>("/api/v1/auth/me"),
        apiPage<Task>(`/api/v1/tasks?${params.toString()}`),
        api<StaffUser[]>("/api/v1/staff/users?limit=200").catch(() => []),
      ]);
      setPermissions(session.permissions ?? []);
      setUserId(session.user_id ?? null);
      setTasks(page.data);
      setStaffUsers(staffRows ?? []);
    } catch (reason) {
      setError(errorMessage(reason, "Tasks could not be loaded."));
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => { void loadTasks(); }, [loadTasks]);

  async function createTask(e: FormEvent) {
    e.preventDefault();
    setBusy("create");
    try {
      const body: Record<string, unknown> = { title: title.trim(), task_type: taskType, priority };
      if (description.trim()) body.description = description.trim();
      if (assigneeId) body.assignee_user_id = assigneeId;
      if (dueAt) body.due_at = new Date(dueAt).toISOString();
      await api("/api/v1/tasks", { method: "POST", headers: writeHeaders(), body: JSON.stringify(body) });
      toast.success("Task created.");
      setTitle(""); setDescription(""); setTaskType("general"); setPriority("normal"); setAssigneeId(""); setDueAt(""); setShowForm(false);
      await loadTasks();
    } catch (reason) { toast.error(errorMessage(reason, "Task could not be created.")); }
    finally { setBusy(null); }
  }

  async function updateStatus(task: Task, newStatus: string) {
    setBusy(task.id);
    try {
      await api(`/api/v1/tasks/${task.id}`, { method: "PATCH", headers: writeHeaders(), body: JSON.stringify({ expected_version: task.version, status: newStatus }) });
      await loadTasks();
    } catch (reason) { toast.error(errorMessage(reason, "Task could not be updated.")); }
    finally { setBusy(null); }
  }

  async function deleteTask(task: Task) {
    const yes = await confirm({ message: `Delete task "${task.title}"?`, danger: true });
    if (!yes) return;
    setBusy(task.id);
    try {
      await api(`/api/v1/tasks/${task.id}`, { method: "DELETE", headers: writeHeaders() });
      toast.success("Task removed.");
      await loadTasks();
    } catch (reason) { toast.error(errorMessage(reason, "Task could not be removed.")); }
    finally { setBusy(null); }
  }

  const listRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (loading || tasks.length === 0 || !listRef.current) return;
    anime({ targets: listRef.current.querySelectorAll(".task-row"), opacity: [0, 1], translateY: [16, 0], duration: 400, delay: anime.stagger(30, { start: 60 }), easing: "easeOutCubic" });
  }, [loading, tasks.length]);

  const priorityColor = (p: string) => p === "urgent" ? "var(--coral)" : p === "high" ? "#e0a458" : p === "low" ? "var(--muted)" : "var(--leaf)";
  const myTasks = tasks.filter((t) => t.assignee_user_id === userId);
  const overdue = tasks.filter((t) => t.due_at && t.status !== "completed" && t.status !== "cancelled" && new Date(t.due_at) < new Date());

  return (
    <section className="dash-content">
      <div className="dash-topline">
        <div>
          <p className="eyebrow">HOME · STAY ON TOP</p>
          <h1>Tasks &amp; <em>to-dos.</em></h1>
        </div>
        <div className="header-actions">
          <button className="button button-secondary" type="button" onClick={() => void loadTasks()} disabled={loading}>Refresh <span>↻</span></button>
          <button className="button button-primary" type="button" onClick={() => setShowForm((v) => !v)}>{showForm ? "Close" : "New task"} <span>＋</span></button>
        </div>
      </div>

      {error && <div className="workspace-alert" role="alert"><strong>{error}</strong></div>}

      <div className="billing-summary">
        <div><span className="eyebrow">MY TASKS</span><strong>{myTasks.length}</strong></div>
        <div><span className="eyebrow">OVERDUE</span><strong style={{ color: overdue.length > 0 ? "var(--coral)" : undefined }}>{overdue.length}</strong></div>
        <div><span className="eyebrow">TOTAL</span><strong>{tasks.length}</strong></div>
      </div>

      <div className="pipeline-toolbar">
        <div className="pipeline-tabs" role="tablist" aria-label="Task status filter">
          {["all", "open", "in_progress", "completed", "cancelled"].map((s) => (
            <button key={s} className={filter === s ? "active" : ""} onClick={() => setFilter(s)}>{statusLabel(s)}</button>
          ))}
        </div>
      </div>

      {showForm && (
        <form className="surface-card" style={{ marginBottom: 16 }} onSubmit={(e) => void createTask(e)}>
          <div className="surface-card-heading"><div><p className="eyebrow">NEW TASK</p><h2>What needs doing?</h2></div></div>
          <div className="form-grid">
            <label>Title *<input required value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Task title" /></label>
            <label>Type<select value={taskType} onChange={(e) => setTaskType(e.target.value)}>{taskTypes.map((t) => <option key={t} value={t}>{statusLabel(t)}</option>)}</select></label>
            <label>Priority<select value={priority} onChange={(e) => setPriority(e.target.value)}>{priorities.map((p) => <option key={p} value={p}>{statusLabel(p)}</option>)}</select></label>
            <label>Assign to<select value={assigneeId} onChange={(e) => setAssigneeId(e.target.value)}><option value="">Unassigned</option>{staffUsers.map((u) => <option key={u.user_id} value={u.user_id}>{u.display_name}</option>)}</select></label>
            <label>Due date<input type="datetime-local" value={dueAt} onChange={(e) => setDueAt(e.target.value)} /></label>
            <label style={{ gridColumn: "1 / -1" }}>Description<textarea value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Details" rows={2} style={{ width: "100%", resize: "vertical" }} /></label>
          </div>
          <div className="form-actions"><button className="button button-primary" type="submit" disabled={busy === "create"}>{busy === "create" ? "Creating…" : "Create task"}</button></div>
        </form>
      )}

      <section className="surface-card">
        <div className="surface-card-heading"><div><p className="eyebrow">TASK LIST</p><h2>{filter === "all" ? "All tasks" : statusLabel(filter)}</h2></div><span className="muted-mono">{tasks.length} TASKS</span></div>

        {loading && <div className="dashboard-empty" role="status"><strong>Loading tasks…</strong></div>}
        {!loading && tasks.length === 0 && <div className="dashboard-empty"><strong>No tasks</strong><span>Create a task to get started.</span></div>}

        {!loading && tasks.length > 0 && (
          <div ref={listRef}>
            {tasks.map((task) => (
              <div className="task-row" key={task.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "14px 0", borderBottom: "1px solid var(--line)", gap: 12 }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                    <span style={{ width: 8, height: 8, borderRadius: "50%", background: priorityColor(task.priority), flexShrink: 0 }} title={task.priority} />
                    <strong style={{ fontSize: 13 }}>{task.title}</strong>
                    <span className={`pipeline-status status-${task.status}`} style={{ fontSize: 10 }}>{statusLabel(task.status)}</span>
                    <span style={{ fontSize: 10, color: "var(--muted)", background: "var(--line)", padding: "1px 6px", borderRadius: 4 }}>{statusLabel(task.task_type)}</span>
                  </div>
                  {task.description && <p style={{ margin: "4px 0 0", fontSize: 12, color: "var(--muted)" }}>{task.description.slice(0, 120)}</p>}
                  <div style={{ display: "flex", gap: 12, marginTop: 4, fontSize: 11, color: "var(--muted)" }}>
                    {task.assignee_name && <span>Assigned: {task.assignee_name}</span>}
                    {task.patient_name && <span>Patient: <Link href={`/patients/${task.patient_id}`}>{task.patient_name}</Link></span>}
                    {task.due_at && <span style={{ color: new Date(task.due_at) < new Date() && task.status !== "completed" ? "var(--coral)" : undefined }}>Due: {formatDateTime(task.due_at)}</span>}
                    <span>Created {formatDate(task.created_at)}</span>
                  </div>
                </div>
                <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
                  {task.status === "open" && <button className="button button-secondary" style={{ fontSize: 11, padding: "4px 10px" }} type="button" disabled={busy === task.id} onClick={() => void updateStatus(task, "in_progress")}>Start</button>}
                  {(task.status === "open" || task.status === "in_progress") && <button className="button button-primary" style={{ fontSize: 11, padding: "4px 10px" }} type="button" disabled={busy === task.id} onClick={() => void updateStatus(task, "completed")}>Done</button>}
                  {task.status === "completed" && <button className="text-control" style={{ fontSize: 11 }} type="button" disabled={busy === task.id} onClick={() => void updateStatus(task, "open")}>Reopen</button>}
                  <button className="ghost-button" style={{ fontSize: 10, color: "var(--coral)", padding: "2px 6px" }} type="button" onClick={() => void deleteTask(task)}>Delete</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </section>
  );
}
