"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { api, errorMessage, post, writeHeaders } from "../_lib/client";
import { useToast } from "../_lib/toast";
import { useConfirm } from "../_lib/confirm";

type SourceCatalog = {
  key: string; label: string; permission: string;
  metrics: { key: string; label: string }[];
  dimensions: { key: string; label: string }[];
  filters: { key: string; type: string }[];
};
type Config = { source: string; metrics: string[]; group_by: string[]; range_preset: string; filters: Record<string, string> };
type SavedReport = { id: string; name: string; description: string | null; source: string; config: Config; status: string; last_run_at: string | null; version: number; created_at: string };
type RunResult = { columns: { key: string; label: string; kind: string }[]; rows: Record<string, unknown>[] };

const RANGES = [["7d", "Last 7 days"], ["30d", "Last 30 days"], ["90d", "Last 90 days"], ["180d", "Last 180 days"], ["365d", "Last 365 days"], ["all", "All time"]];
const TEMPLATES: { label: string; config: Config }[] = [
  { label: "Appointments by day", config: { source: "appointments", metrics: ["count", "completed", "cancelled"], group_by: ["day"], range_preset: "30d", filters: {} } },
  { label: "Package utilization", config: { source: "package_sales", metrics: ["count", "sessions_purchased", "sessions_used", "sessions_remaining"], group_by: [], range_preset: "90d", filters: {} } },
  { label: "Cash collected by method", config: { source: "payments", metrics: ["collected_minor", "payment_count"], group_by: ["method"], range_preset: "30d", filters: {} } },
  { label: "Invoiced by month", config: { source: "invoices", metrics: ["invoiced_minor", "invoice_count", "paid_count"], group_by: ["month"], range_preset: "365d", filters: {} } },
];

const EMPTY = (source: string): Config => ({ source, metrics: [], group_by: [], range_preset: "30d", filters: {} });

export default function ReportBuilder({ canManage }: { canManage: boolean }) {
  const toast = useToast();
  const confirm = useConfirm();
  const [sources, setSources] = useState<SourceCatalog[]>([]);
  const [saved, setSaved] = useState<SavedReport[]>([]);
  const [config, setConfig] = useState<Config | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [editing, setEditing] = useState<{ id: string; version: number } | null>(null);
  const [preview, setPreview] = useState<RunResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [cat, list] = await Promise.all([
        api<SourceCatalog[]>("/api/v1/reports/sources"),
        api<SavedReport[]>("/api/v1/reports"),
      ]);
      setSources(cat);
      setSaved(list);
      setConfig((c) => c ?? EMPTY(cat[0]?.key ?? "appointments"));
    } catch (reason) {
      setError(errorMessage(reason, "The report builder could not be loaded."));
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const source = useMemo(() => sources.find((s) => s.key === config?.source), [sources, config]);

  function pickSource(key: string) { setConfig(EMPTY(key)); setPreview(null); }
  function toggleMetric(key: string) {
    setConfig((c) => c && ({ ...c, metrics: c.metrics.includes(key) ? c.metrics.filter((m) => m !== key) : [...c.metrics, key] }));
  }
  function toggleGroup(key: string) {
    setConfig((c) => {
      if (!c) return c;
      if (c.group_by.includes(key)) return { ...c, group_by: c.group_by.filter((g) => g !== key) };
      if (c.group_by.length >= 2) return c;
      return { ...c, group_by: [...c.group_by, key] };
    });
  }
  function loadConfig(cfg: Config) { setConfig({ ...EMPTY(cfg.source), ...cfg, filters: { ...cfg.filters } }); setPreview(null); }
  function applyTemplate(cfg: Config) { setEditing(null); setName(""); setDescription(""); loadConfig(cfg); }

  async function act(fn: () => Promise<unknown>, success: string, fallback: string): Promise<boolean> {
    setBusy(true); setError(null);
    try { await fn(); if (success) toast.success(success); return true; }
    catch (reason) { toast.error(errorMessage(reason, fallback)); return false; }
    finally { setBusy(false); }
  }

  function cleanConfig(c: Config): Config {
    const filters = Object.fromEntries(Object.entries(c.filters).filter(([, v]) => v.trim() !== ""));
    return { ...c, filters };
  }

  async function runPreview() {
    if (!config || config.metrics.length === 0) { setError("Choose at least one metric."); return; }
    await act(async () => { setPreview(await post<RunResult>("/api/v1/reports/run", cleanConfig(config))); }, "", "The report could not be run.");
  }

  function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!config || config.metrics.length === 0) { setError("Choose at least one metric."); return; }
    const body = { name: name.trim(), description: description.trim() || null, config: cleanConfig(config) };
    const op = editing
      ? () => api(`/api/v1/reports/${editing.id}`, { method: "PUT", headers: writeHeaders(), body: JSON.stringify({ ...body, expected_version: editing.version }) })
      : () => post("/api/v1/reports", body);
    void act(op, editing ? "Report updated." : "Report saved.", "The report could not be saved.").then((ok) => {
      if (ok) { setEditing(null); setName(""); setDescription(""); void load(); }
    });
  }

  function openSaved(r: SavedReport) {
    setEditing({ id: r.id, version: r.version });
    setName(r.name); setDescription(r.description ?? "");
    loadConfig(r.config);
  }

  async function runSaved(r: SavedReport) {
    await act(async () => {
      const result = await post<{ columns: RunResult["columns"]; rows: RunResult["rows"] }>(`/api/v1/reports/${r.id}/run`);
      setPreview({ columns: result.columns, rows: result.rows });
    }, "", "The report could not be run.");
    void load();
  }

  async function duplicate(r: SavedReport) {
    const dupName = window.prompt("Name for the duplicate", `${r.name} copy`);
    if (!dupName) return;
    void act(() => post(`/api/v1/reports/${r.id}/duplicate`, { name: dupName.trim() }), "Report duplicated.", "The report could not be duplicated.").then((ok) => { if (ok) void load(); });
  }

  async function archive(r: SavedReport) {
    const ok = await confirm({ title: `Archive ${r.name}`, message: "The report definition is hidden from the list. It is not deleted and can be restored later.", danger: true, confirmLabel: "Archive" });
    if (!ok) return;
    void act(() => post(`/api/v1/reports/${r.id}/archive`), "Report archived.", "The report could not be archived.").then((done) => { if (done) { if (editing?.id === r.id) setEditing(null); void load(); } });
  }

  async function exportCsv(r: SavedReport) {
    try {
      const res = await fetch(`/api/v1/reports/${r.id}/export`, { credentials: "include", headers: { "ngrok-skip-browser-warning": "1" } });
      if (!res.ok) throw new Error("Export failed");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url; link.download = `${r.name}.csv`;
      document.body.appendChild(link); link.click(); link.remove();
      URL.revokeObjectURL(url);
    } catch (reason) {
      toast.error(errorMessage(reason, "The CSV could not be exported."));
    }
  }

  function printResult(title: string, result: RunResult) {
    const win = window.open("", "_blank", "width=900,height=700");
    if (!win) { toast.error("Allow pop-ups to print or save this report as PDF."); return; }
    const esc = (v: unknown) => String(v ?? "—").replace(/[&<>]/g, (ch) => (({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }) as Record<string, string>)[ch]);
    const head = result.columns.map((c) => `<th>${esc(c.label)}</th>`).join("");
    const body = result.rows.map((row) => `<tr>${result.columns.map((c) => `<td>${esc(row[c.key])}</td>`).join("")}</tr>`).join("");
    win.document.write(`<!doctype html><html><head><title>${esc(title)}</title><style>body{font-family:'DM Sans',system-ui,sans-serif;padding:28px;color:#1c2928}h1{font:500 20px Georgia,serif}table{border-collapse:collapse;width:100%;font-size:13px;margin-top:14px}th,td{border:1px solid #e1e1de;padding:8px 10px;text-align:left}th{background:#f3f4f2;font-size:11px;letter-spacing:.04em}</style></head><body><h1>${esc(title)}</h1><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table><script>window.onload=function(){window.print();};</script></body></html>`);
    win.document.close();
  }

  if (!config) return <section className="surface-card report-card"><div className="dashboard-empty"><strong>Loading report builder…</strong><span>Fetching available data sources.</span></div></section>;

  return <div className="report-builder">
    {error && <div className="workspace-alert" role="alert"><strong>{error}</strong></div>}
    <div className="report-builder-grid">
      <section className="surface-card report-card">
        <div className="surface-card-heading"><div><p className="eyebrow">{editing ? "EDIT REPORT" : "CREATE REPORT"}</p><h2>Report builder</h2></div>
          {editing && <button className="text-control" onClick={() => { setEditing(null); setName(""); setDescription(""); }}>New report</button>}
        </div>
        <div className="report-templates">{TEMPLATES.map((t) => <button key={t.label} className="report-template-chip" onClick={() => applyTemplate(t.config)}>{t.label}</button>)}</div>
        <form className="manage-form packages-form" onSubmit={handleSave}>
          <label>Data source<select value={config.source} onChange={(e) => pickSource(e.target.value)}>{sources.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}</select></label>
          <fieldset className="report-fieldset"><legend>Metrics</legend>{source?.metrics.map((m) => <label key={m.key} className="report-check"><input type="checkbox" checked={config.metrics.includes(m.key)} onChange={() => toggleMetric(m.key)} />{m.label}</label>)}</fieldset>
          <fieldset className="report-fieldset"><legend>Group by <span className="field-optional">up to 2</span></legend>{source?.dimensions.map((d) => <label key={d.key} className="report-check"><input type="checkbox" checked={config.group_by.includes(d.key)} onChange={() => toggleGroup(d.key)} />{d.label}</label>)}</fieldset>
          <label>Date range<select value={config.range_preset} onChange={(e) => setConfig({ ...config, range_preset: e.target.value })}>{RANGES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
          {source && source.filters.length > 0 && <fieldset className="report-fieldset"><legend>Filters <span className="field-optional">optional</span></legend>{source.filters.map((f) => <label key={f.key} className="report-filter">{f.key}<input value={config.filters[f.key] ?? ""} placeholder={f.type === "uuid" ? "exact id" : "exact value"} onChange={(e) => setConfig({ ...config, filters: { ...config.filters, [f.key]: e.target.value } })} /></label>)}</fieldset>}
          <div className="report-builder-actions">
            <button type="button" className="button button-secondary" disabled={busy} onClick={() => void runPreview()}>Preview</button>
            {canManage && <>
              <input className="report-name-input" placeholder="Report name" value={name} onChange={(e) => setName(e.target.value)} required />
              <button type="submit" className="button button-primary" disabled={busy || !name.trim()}>{editing ? "Update" : "Save report"}<span>↗</span></button>
            </>}
          </div>
          {canManage && <input className="report-name-input" placeholder="Description (optional)" value={description} onChange={(e) => setDescription(e.target.value)} />}
        </form>
      </section>

      <section className="surface-card report-card">
        <div className="surface-card-heading"><div><p className="eyebrow">PREVIEW</p><h2>Result</h2></div>
          {preview && preview.rows.length > 0 && <button className="text-control" onClick={() => printResult(name.trim() || "Report preview", preview)}>Print / PDF</button>}
        </div>
        {!preview ? <div className="dashboard-empty"><strong>No preview yet</strong><span>Choose metrics and press Preview.</span></div>
          : preview.rows.length === 0 ? <div className="dashboard-empty"><strong>No rows</strong><span>No data matched this configuration and range.</span></div>
            : <div className="report-table-wrap"><table className="report-table"><thead><tr>{preview.columns.map((c) => <th key={c.key}>{c.label}</th>)}</tr></thead>
              <tbody>{preview.rows.map((row, i) => <tr key={i}>{preview.columns.map((c) => <td key={c.key}>{row[c.key] === null || row[c.key] === undefined ? "—" : String(row[c.key])}</td>)}</tr>)}</tbody></table></div>}
      </section>
    </div>

    <section className="surface-card report-card" style={{ marginTop: 20 }}>
      <div className="surface-card-heading"><div><p className="eyebrow">SAVED REPORTS</p><h2>Your clinic&apos;s reports</h2></div><span className="muted-mono">{saved.length} SAVED</span></div>
      <div className="invoice-list">
        {saved.length === 0 && <div className="dashboard-empty"><strong>No saved reports</strong><span>Build a report above and save it to reuse later.</span></div>}
        {saved.map((r) => <article className="invoice-row" key={r.id}>
          <div className="invoice-mark">{r.name.slice(0, 2).toUpperCase()}</div>
          <div className="invoice-main">
            <h3>{r.name}</h3>
            <p>{r.source} · {r.config.metrics.length} metric{r.config.metrics.length === 1 ? "" : "s"}{r.config.group_by.length ? ` · by ${r.config.group_by.join(", ")}` : ""}</p>
            <small className="muted-mono">{r.last_run_at ? `Last run ${new Date(r.last_run_at).toLocaleString()}` : "Never run"}</small>
          </div>
          <div className="invoice-actions report-saved-actions">
            <button className="button button-secondary" disabled={busy} onClick={() => void runSaved(r)}>Run</button>
            <button className="text-control" onClick={() => void exportCsv(r)}>CSV</button>
            {canManage && <button className="text-control" onClick={() => openSaved(r)}>Edit</button>}
            {canManage && <button className="text-control" onClick={() => void duplicate(r)}>Duplicate</button>}
            {canManage && <button className="text-control" onClick={() => void archive(r)}>Archive</button>}
          </div>
        </article>)}
      </div>
    </section>
  </div>;
}
