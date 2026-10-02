"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, errorMessage, label, money, post } from "../_lib/client";

type Summary = { date: string; payment_methods: { method: string; payments: number; collected_minor: number }[]; collected_minor: number; invoices: number; invoiced_minor: number; expenses_minor: number | null; net_minor: number | null };
type Expense = { id: string; category: string; description: string; amount_minor: number; currency: string; incurred_on: string; voided_at: string | null };
type Session = { permissions?: string[] };
const CATEGORIES = ["rent", "salaries", "utilities", "supplies", "equipment", "marketing", "maintenance", "other"];
const today = () => new Date().toISOString().slice(0, 10);

export default function FinancePage() {
  const [day, setDay] = useState(today());
  const [summary, setSummary] = useState<Summary | null>(null);
  const [expenses, setExpenses] = useState<Expense[]>([]);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const session = await api<Session>("/api/v1/auth/me");
      const granted = session.permissions ?? [];
      setPermissions(granted);
      const [summaryRow, expenseRows] = await Promise.all([
        api<Summary>(`/api/v1/finance/cashier-summary?date=${day}`),
        granted.includes("expense.read") ? api<Expense[]>("/api/v1/finance/expenses?limit=100") : Promise.resolve([]),
      ]);
      setSummary(summaryRow);
      setExpenses(expenseRows ?? []);
    } catch (reason) {
      setError(errorMessage(reason, "Finance data could not be loaded."));
    } finally {
      setLoading(false);
    }
  }, [day]);
  useEffect(() => { void load(); }, [load]);

  async function addExpense(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const amount = Math.round(Number(form.get("amount")) * 100);
    if (!Number.isFinite(amount) || amount <= 0) { setError("Enter a positive amount."); return; }
    setBusy(true);
    setError(null);
    try {
      await post("/api/v1/finance/expenses", { category: form.get("category"), description: String(form.get("description")).trim(), amount_minor: amount, currency: "PKR", incurred_on: form.get("date") });
      setShowForm(false);
      await load();
    } catch (reason) {
      setError(errorMessage(reason, "The expense could not be saved."));
    } finally {
      setBusy(false);
    }
  }
  async function voidExpense(id: string) {
    const reason = window.prompt("Why is this expense being voided?");
    if (!reason || reason.trim().length < 3) return;
    try { await post(`/api/v1/finance/expenses/${id}/void`, { reason: reason.trim() }); await load(); } catch (failure) { setError(errorMessage(failure, "The expense could not be voided.")); }
  }

  const canManage = permissions.includes("expense.manage");
  return <main className="workspace-page finance-page">
    <div className="workspace-page-header"><div><p className="eyebrow">BUSINESS · END OF DAY</p><h1>Close the day <em>with confidence.</em></h1><p className="workspace-page-intro">Cashier summary by payment method, with optional clinic expenses for a basic profitability view.</p></div><div className="header-actions"><label className="report-period">Day<input type="date" value={day} max={today()} onChange={(event) => setDay(event.target.value || today())} /></label><button className="button button-secondary" onClick={() => void load()} disabled={loading}>Refresh <span>↻</span></button></div></div>
    {error && <div className="workspace-alert" role="alert"><strong>{error}</strong><button className="ghost-button" onClick={() => void load()}>Try again <span>→</span></button></div>}
    {summary && <div className="billing-summary"><div><span className="eyebrow">COLLECTED</span><strong>{money(summary.collected_minor)}</strong><small className="muted-mono">{summary.payment_methods.reduce((total, row) => total + row.payments, 0)} PAYMENTS</small></div><div><span className="eyebrow">INVOICED</span><strong>{money(summary.invoiced_minor)}</strong><small className="muted-mono">{summary.invoices} INVOICES</small></div><div><span className="eyebrow">{summary.net_minor == null ? "EXPENSES" : "NET"}</span><strong>{summary.net_minor == null ? "Restricted" : money(summary.net_minor)}</strong><small className="muted-mono">{summary.expenses_minor == null ? "NO expense.read" : `${money(summary.expenses_minor)} SPENT`}</small></div></div>}
    {summary && <section className="surface-card"><div className="surface-card-heading"><div><p className="eyebrow">PAYMENT METHODS</p><h2>How money arrived.</h2></div><span className="muted-mono">{summary.date}</span></div><div className="report-list">{summary.payment_methods.length === 0 && <div className="dashboard-empty"><strong>No payments on this day</strong></div>}{summary.payment_methods.map((row) => <div className="report-list-row" key={row.method}><span>{label(row.method)} · {row.payments}</span><strong>{money(row.collected_minor)}</strong></div>)}</div></section>}
    {permissions.includes("expense.read") && <section className="surface-card"><div className="surface-card-heading"><div><p className="eyebrow">EXPENSES</p><h2>What the clinic spent.</h2></div>{canManage && <button className="button button-primary" onClick={() => setShowForm((value) => !value)}>Add expense <span>＋</span></button>}</div>
      {showForm && <form className="manage-form" onSubmit={addExpense}><div className="form-grid"><label>Category<select name="category" defaultValue="supplies">{CATEGORIES.map((item) => <option key={item} value={item}>{label(item)}</option>)}</select></label><label>Description<input name="description" required maxLength={500} /></label><label>Amount (PKR)<input name="amount" type="number" min={0} step="0.01" required /></label><label>Date<input name="date" type="date" defaultValue={today()} required /></label></div><div className="form-actions"><button className="button button-primary" type="submit" disabled={busy}>{busy ? "Saving…" : "Save expense"}<span>↗</span></button></div></form>}
      <div className="invoice-list">{!loading && expenses.length === 0 && <div className="dashboard-empty"><strong>No expenses recorded</strong></div>}{expenses.map((item) => <article className="invoice-row" key={item.id}><div className="invoice-mark">{item.category.slice(0, 3).toUpperCase()}</div><div className="invoice-main"><h3>{item.description}</h3><p>{label(item.category)} · {item.incurred_on}</p></div><div className="invoice-actions"><strong>{money(item.amount_minor, item.currency)}</strong>{item.voided_at ? <span className="pipeline-status status-void">void</span> : canManage && <button className="text-control" onClick={() => void voidExpense(item.id)}>Void</button>}</div></article>)}</div></section>}
  </main>;
}
