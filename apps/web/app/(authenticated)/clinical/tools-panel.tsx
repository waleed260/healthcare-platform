"use client";

import { useCallback, useEffect, useState } from "react";
import { api, errorMessage } from "../_lib/client";

type ToolState = { tool_key: string; state: Record<string, unknown>; version: number; updated_at: string };
// eslint-disable-next-line no-unused-vars
type OnError = (message: string) => void;
type Props = { patientId: string; permissions: string[]; onError: OnError };

const TOOLS = [
  { key: "dental_chart", label: "Dental chart" },
  { key: "norwood", label: "Norwood scale" },
  { key: "graft_plan", label: "Graft plan" },
  { key: "skin_map", label: "Skin map" },
] as const;

const TOOTH_STATES = ["healthy", "caries", "filled", "crown", "implant", "root_canal", "missing"] as const;
const TOOTH_ABBR: Record<string, string> = { healthy: "·", caries: "C", filled: "F", crown: "Cr", implant: "Im", root_canal: "RC", missing: "✕" };
const QUADRANTS = [[18,17,16,15,14,13,12,11],[21,22,23,24,25,26,27,28],[48,47,46,45,44,43,42,41],[31,32,33,34,35,36,37,38]];
const NORWOOD = ["I","II","IIa","III","IIIa","III_vertex","IV","IVa","V","Va","VI","VII"];
const GRAFT_ZONES = [["hairline","Hairline"],["temporal_left","Temporal L"],["temporal_right","Temporal R"],["midscalp","Mid-scalp"],["crown","Crown"]];
const SKIN_REGIONS = [["forehead","Forehead"],["glabella","Glabella"],["nose","Nose"],["cheek_left","Cheek L"],["cheek_right","Cheek R"],["perioral","Perioral"],["chin","Chin"],["jaw_left","Jaw L"],["jaw_right","Jaw R"],["neck","Neck"]];
const SKIN_CONCERNS = ["acne","scarring","pigmentation","redness","wrinkles","dryness","oiliness","laxity","pores"];

export default function ToolsPanel({ patientId, permissions, onError }: Props) {
  const canEdit = permissions.includes("clinical.manage");
  const canRead = permissions.includes("clinical.read");
  const [active, setActive] = useState<string>("dental_chart");
  const [states, setStates] = useState<Record<string, ToolState>>({});
  const [draft, setDraft] = useState<Record<string, unknown>>({});
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!patientId || !canRead) return;
    try {
      const rows = await api<ToolState[]>(`/api/v1/patients/${patientId}/tool-states`);
      const map: Record<string, ToolState> = {};
      (Array.isArray(rows) ? rows : []).forEach((r) => { map[r.tool_key] = r; });
      setStates(map);
      setDraft((map[active]?.state as Record<string, unknown>) ?? {});
    } catch (reason) { onError(errorMessage(reason, "Clinical tools could not be loaded.")); }
  }, [patientId, permissions.join(","), active]);
  useEffect(() => { void load(); }, [load]);

  const save = async () => {
    setBusy(true); setNotice(null);
    try {
      const saved = await api<ToolState>(`/api/v1/patients/${patientId}/tool-states/${active}`, { method: "PUT", headers: { "Content-Type": "application/json", "X-CSRF-Token": document.cookie.split(";").map((p) => p.trim()).find((p) => p.startsWith("csrf_token="))?.slice(11) ?? "" }, body: JSON.stringify({ tool_key: active, state: draft }) });
      setStates((s) => ({ ...s, [active]: saved }));
      setDraft((saved.state as Record<string, unknown>) ?? {});
      setNotice("Saved.");
    } catch (reason) { onError(errorMessage(reason, "The tool state could not be saved.")); } finally { setBusy(false); }
  };

  const notes = (draft.notes as string) ?? "";
  const setNotes = (v: string) => setDraft((d) => ({ ...d, notes: v }));

  // dental
  const teeth = (draft.teeth as Record<string, string>) ?? {};
  const cycleTooth = (n: number) => { const cur = teeth[String(n)] ?? "healthy"; const next = TOOTH_STATES[(TOOTH_STATES.indexOf(cur as typeof TOOTH_STATES[number]) + 1) % TOOTH_STATES.length]; const copy = { ...teeth }; if (next === "healthy") delete copy[String(n)]; else copy[String(n)] = next; setDraft((d) => ({ ...d, teeth: copy })); };
  // graft
  const zones = (draft.zones as Record<string, number>) ?? {};
  const setZone = (z: string, v: number) => setDraft((d) => ({ ...d, zones: { ...zones, [z]: v } }));
  const graftTotal = Object.values(zones).reduce((a, b) => a + (Number(b) || 0), 0);
  // skin
  const regions = (draft.regions as Record<string, string[]>) ?? {};
  const toggleConcern = (region: string, concern: string) => { const cur = regions[region] ?? []; const next = cur.includes(concern) ? cur.filter((c) => c !== concern) : [...cur, concern]; setDraft((d) => ({ ...d, regions: { ...regions, [region]: next } })); };

  if (!canRead) return <section className="surface-card"><div className="dashboard-empty"><strong>No access</strong><span>Your role cannot view clinical tools.</span></div></section>;

  return <section className="surface-card tools-panel">
    <div className="surface-card-heading"><div><p className="eyebrow">SPECIALTY TOOLS</p><h2>Structured clinical assessments.</h2></div></div>
    {notice && <div className="permission-strip" aria-live="polite"><span className="permission-ok">{notice}</span></div>}
    <div className="pipeline-toolbar"><div className="pipeline-tabs" role="tablist">{TOOLS.map((t) => <button key={t.key} role="tab" aria-selected={active === t.key} className={active === t.key ? "active" : ""} onClick={() => { setActive(t.key); setDraft((states[t.key]?.state as Record<string, unknown>) ?? {}); setNotice(null); }}>{t.label}{states[t.key] ? " ✓" : ""}</button>)}</div></div>

    {active === "dental_chart" && <div className="dental-chart">{QUADRANTS.map((q, qi) => <div className="dental-row" key={qi}>{q.map((n) => { const st = teeth[String(n)] ?? "healthy"; return <button key={n} type="button" className={`tooth tooth-${st}`} disabled={!canEdit} title={`Tooth ${n}: ${st.replace("_", " ")}`} onClick={() => cycleTooth(n)}><b>{n}</b><span>{TOOTH_ABBR[st]}</span></button>; })}</div>)}<p className="field-note">Click a tooth to cycle: healthy → caries → filled → crown → implant → root canal → missing.</p></div>}

    {active === "norwood" && <div className="form-grid"><label>Hair-loss stage<select value={(draft.stage as string) ?? ""} disabled={!canEdit} onChange={(e) => setDraft((d) => ({ ...d, stage: e.target.value || null }))}><option value="">Not set</option>{NORWOOD.map((s) => <option key={s} value={s}>{s.replace("_", " ")}</option>)}</select></label></div>}

    {active === "graft_plan" && <div><div className="form-grid">{GRAFT_ZONES.map(([z, lbl]) => <label key={z}>{lbl}<input type="number" min={0} max={20000} value={zones[z] ?? ""} disabled={!canEdit} onChange={(e) => setZone(z, Math.max(0, Math.min(20000, Number(e.target.value) || 0)))} /></label>)}</div><p className="field-note">Total grafts: <strong>{graftTotal}</strong></p></div>}

    {active === "skin_map" && <div className="skin-map">{SKIN_REGIONS.map(([r, lbl]) => <div className="skin-region" key={r}><strong>{lbl}</strong><div className="skin-chips">{SKIN_CONCERNS.map((c) => <button key={c} type="button" disabled={!canEdit} className={`chip ${(regions[r] ?? []).includes(c) ? "chip-on" : ""}`} onClick={() => toggleConcern(r, c)}>{c}</button>)}</div></div>)}</div>}

    <label className="font-field" style={{ marginTop: 14 }}>Notes<textarea rows={3} value={notes} maxLength={5000} disabled={!canEdit} onChange={(e) => setNotes(e.target.value)} /></label>
    {canEdit && <div className="form-actions"><button className="button button-primary" onClick={() => void save()} disabled={busy}>{busy ? "Saving…" : "Save assessment"}</button></div>}
  </section>;
}
