"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import anime from "animejs";
import { api, errorMessage, label, money, post, writeHeaders } from "../_lib/client";
import { useToast } from "../_lib/toast";
import { useConfirm } from "../_lib/confirm";

type Summary = { date: string; payment_methods: { method: string; payments: number; collected_minor: number }[]; collected_minor: number; invoices: number; invoiced_minor: number; expenses_minor: number | null; net_minor: number | null };
type Expense = { id: string; category: string; description: string; amount_minor: number; currency: string; incurred_on: string; voided_at: string | null };
type Session = { permissions?: string[] };
type Revenue = { start: string; end: string; providers: { provider_id: string | null; provider_name: string; revenue_minor: number; percent_bp: number | null; commission_minor: number }[]; total_revenue_minor: number; total_commission_minor: number };
type Rule = { doctor_id: string; public_name: string; percent_bp: number; active: boolean };
const CATEGORIES = ["rent", "salaries", "utilities", "supplies", "equipment", "marketing", "maintenance", "other"];
const today = () => new Date().toISOString().slice(0, 10);

export default function FinancePage() {
  const toast = useToast();
  const confirm = useConfirm();
  const [day, setDay] = useState(today());
  const [summary, setSummary] = useState<Summary | null>(null);
  const [expenses, setExpenses] = useState<Expense[]>([]);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [revenue, setRevenue] = useState<Revenue | null>(null);
  const [rules, setRules] = useState<Rule[]>([]);
  const [rangeStart, setRangeStart] = useState(() => new Date(Date.now() - 29 * 86400000).toISOString().slice(0, 10));

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
      const [revenueRow, ruleRows] = await Promise.all([api<Revenue>(`/api/v1/finance/provider-revenue?start=${rangeStart}&end=${day}`).catch(() => null), api<Rule[]>("/api/v1/finance/commission-rules").catch(() => [])]);
      setRevenue(revenueRow && typeof revenueRow === "object" && "providers" in revenueRow ? revenueRow : null);
      setRules(Array.isArray(ruleRows) ? ruleRows : []);
      setExpenses(expenseRows ?? []);
    } catch (reason) {
      setError(errorMessage(reason, "Finance data could not be loaded."));
    } finally {
      setLoading(false);
    }
  }, [day, rangeStart]);
  useEffect(() => { void load(); }, [load]);

  async function addExpense(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const amount = Math.round(Number(form.get("amount")) * 100);
    if (!Number.isFinite(amount) || amount <= 0) { toast.error("Enter a positive amount."); return; }
    setBusy(true);
    try {
      await post("/api/v1/finance/expenses", { category: form.get("category"), description: String(form.get("description")).trim(), amount_minor: amount, currency: "PKR", incurred_on: form.get("date") });
      setShowForm(false);
      toast.success("Expense recorded.");
      await load();
    } catch (reason) {
      toast.error(errorMessage(reason, "The expense could not be saved."));
    } finally {
      setBusy(false);
    }
  }

  async function voidExpense(id: string) {
    const yes = await confirm({ message: "Void this expense? This action cannot be undone.", title: "Void expense", confirmLabel: "Void", danger: true });
    if (!yes) return;
    const reason = window.prompt("Why is this expense being voided?");
    if (!reason || reason.trim().length < 3) { toast.error("A reason of at least 3 characters is required."); return; }
    try {
      await post(`/api/v1/finance/expenses/${id}/void`, { reason: reason.trim() });
      toast.success("Expense voided.");
      await load();
    } catch (failure) {
      toast.error(errorMessage(failure, "The expense could not be voided."));
    }
  }

  const canManage = permissions.includes("expense.manage");

  async function saveRule(rule: Rule, percent: number, active: boolean) {
    try {
      await api(`/api/v1/finance/commission-rules/${rule.doctor_id}`, { method: "PUT", headers: writeHeaders(), body: JSON.stringify({ percent_bp: Math.round(percent * 100), active }) });
      toast.success(`Commission updated for ${rule.public_name}.`);
      await load();
    } catch (failure) {
      toast.error(errorMessage(failure, "The commission rule could not be saved."));
    }
  }

  const financeRef = useRef<HTMLElement>(null);
  useEffect(() => {
    if (loading || !financeRef.current) return;
    anime({
      targets: financeRef.current.querySelectorAll(".surface-card, .panel-card"),
      opacity: [0, 1],
      translateY: [24, 0],
      duration: 500,
      delay: anime.stagger(60, { start: 100 }),
      easing: "easeOutCubic",
    });
  }, [loading]);

  return (
    <section className="dash-content finance-content" ref={financeRef} aria-busy={loading}>
      <div className="dash-topline">
        <div>
          <p className="eyebrow">BUSINESS · END OF DAY</p>
          <h1>Close the day <em>with confidence.</em></h1>
          <p className="workspace-page-intro">Cashier summary by payment method, with optional clinic expenses for a basic profitability view.</p>
        </div>
        <div className="header-actions">
          <label className="report-period">Day <input type="date" value={day} max={today()} onChange={(e) => setDay(e.target.value || today())} /></label>
          <button className="button button-secondary" type="button" onClick={() => void load()} disabled={loading}>Refresh <span>↻</span></button>
        </div>
      </div>

      {error && <div className="workspace-alert" role="alert"><strong>{error}</strong><button className="ghost-button" type="button" onClick={() => void load()}>Try again <span>→</span></button></div>}

      {summary && (
        <div className="billing-summary">
          <div><span className="eyebrow">COLLECTED</span><strong>{money(summary.collected_minor)}</strong><small className="muted-mono">{summary.payment_methods.reduce((t, r) => t + r.payments, 0)} PAYMENTS</small></div>
          <div><span className="eyebrow">INVOICED</span><strong>{money(summary.invoiced_minor)}</strong><small className="muted-mono">{summary.invoices} INVOICES</small></div>
          <div><span className="eyebrow">{summary.net_minor == null ? "EXPENSES" : "NET"}</span><strong>{summary.net_minor == null ? "Restricted" : money(summary.net_minor)}</strong><small className="muted-mono">{summary.expenses_minor == null ? "NO expense.read" : `${money(summary.expenses_minor)} SPENT`}</small></div>
        </div>
      )}

      {summary && (
        <section className="surface-card">
          <div className="surface-card-heading"><div><p className="eyebrow">PAYMENT METHODS</p><h2>How money arrived.</h2></div><span className="muted-mono">{summary.date}</span></div>
          <div className="report-list">
            {summary.payment_methods.length === 0 && <div className="dashboard-empty"><strong>No payments on this day</strong></div>}
            {summary.payment_methods.map((row) => <div className="report-list-row" key={row.method}><span>{label(row.method)} · {row.payments}</span><strong>{money(row.collected_minor)}</strong></div>)}
          </div>
        </section>
      )}

      {revenue && (
        <section className="surface-card">
          <div className="surface-card-heading"><div><p className="eyebrow">PROVIDER REVENUE</p><h2>Who earned what.</h2></div><label className="report-period">From <input type="date" value={rangeStart} max={day} onChange={(e) => setRangeStart(e.target.value || rangeStart)} /></label></div>
          <div className="report-list">
            {revenue.providers.length === 0 && <div className="dashboard-empty"><strong>No payments in this range</strong></div>}
            {revenue.providers.map((row) => <div className="report-list-row" key={row.provider_id ?? "none"}><span>{row.provider_name}{row.percent_bp ? ` · ${(row.percent_bp / 100).toFixed(2)}%` : ""}</span><strong>{money(row.revenue_minor)}{row.commission_minor > 0 ? ` · commission ${money(row.commission_minor)}` : ""}</strong></div>)}
          </div>
          {rules.length > 0 && (
            <div className="report-mini-list">
              <strong>Commission rules (% of collected revenue)</strong>
              {rules.map((rule) => (
                <div className="theme-row" key={rule.doctor_id}>
                  <span>{rule.public_name}</span>
                  <input aria-label={`Commission percent for ${rule.public_name}`} type="number" min={0} max={100} step={0.5} defaultValue={rule.percent_bp / 100} disabled={!permissions.includes("billing.manage")} onBlur={(e) => { const v = Number(e.target.value); if (Number.isFinite(v) && v !== rule.percent_bp / 100) void saveRule(rule, v, v > 0); }} />
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {permissions.includes("expense.read") && (
        <section className="surface-card">
          <div className="surface-card-heading"><div><p className="eyebrow">EXPENSES</p><h2>What the clinic spent.</h2></div>{canManage && <button className="button button-primary" type="button" onClick={() => setShowForm((v) => !v)}>Add expense <span>＋</span></button>}</div>
          {showForm && (
            <form className="manage-form" onSubmit={(e) => void addExpense(e)}>
              <div className="form-grid">
                <label>Category <select name="category" defaultValue="supplies">{CATEGORIES.map((c) => <option key={c} value={c}>{label(c)}</option>)}</select></label>
                <label>Description <input name="description" required maxLength={500} /></label>
                <label>Amount (PKR) <input name="amount" type="number" min={0} step="0.01" required /></label>
                <label>Date <input name="date" type="date" defaultValue={today()} required /></label>
              </div>
              <div className="form-actions">
                <button className="button button-primary" type="submit" disabled={busy}>{busy ? "Saving…" : "Save expense"} <span>↗</span></button>
              </div>
            </form>
          )}
          <div className="invoice-list">
            {!loading && expenses.length === 0 && <div className="dashboard-empty"><strong>No expenses recorded</strong></div>}
            {expenses.map((item) => (
              <article className="invoice-row" key={item.id}>
                <div className="invoice-mark">{item.category.slice(0, 3).toUpperCase()}</div>
                <div className="invoice-main"><h3>{item.description}</h3><p>{label(item.category)} · {item.incurred_on}</p></div>
                <div className="invoice-actions">
                  <strong>{money(item.amount_minor, item.currency)}</strong>
                  {item.voided_at ? <span className="pipeline-status status-void">void</span> : canManage && <button className="text-control" type="button" onClick={() => void voidExpense(item.id)}>Void</button>}
                </div>
              </article>
            ))}
          </div>
        </section>
      )}
    </section>
  );
}
