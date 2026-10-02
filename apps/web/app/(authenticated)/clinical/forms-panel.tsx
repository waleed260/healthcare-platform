"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, errorMessage, label, patch, post } from "../_lib/client";

type FieldType = "text" | "textarea" | "number" | "select" | "checkbox" | "date" | "media_ref";
type Field = { key: string; label: string; type: FieldType; required: boolean; options: string[] };
type Template = { id: string; form_key: string; name: string; specialty_id: string | null; field_schema: { fields: Field[] }; status: string; version: number };
type Response = { id: string; template_id: string; form_key: string; name: string; response_data: Record<string, unknown>; status: string; submitted_at: string | null; version: number; updated_at: string };

const FIELD_TYPES: FieldType[] = ["text", "textarea", "number", "select", "checkbox", "date", "media_ref"];
const list = <T,>(v: unknown): T[] => (Array.isArray(v) ? (v as T[]) : []);
const slugKey = (name: string, i: number) => name.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "").slice(0, 40) || `field_${i}`;

// eslint-disable-next-line no-unused-vars
type Notify = (message: string) => void;

export default function FormsPanel({ patientId, permissions, onError }: { patientId: string; permissions: string[]; onError: Notify }) {
  const can = (p: string) => permissions.includes(p);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [responses, setResponses] = useState<Response[]>([]);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [showBuilder, setShowBuilder] = useState(false);
  const [draftFields, setDraftFields] = useState<Field[]>([{ key: "field_0", label: "New field", type: "text", required: false, options: [] }]);
  const [fillTemplateId, setFillTemplateId] = useState("");
  const [openResponse, setOpenResponse] = useState<Response | null>(null);
  const [answers, setAnswers] = useState<Record<string, unknown>>({});

  const load = useCallback(async () => {
    if (!patientId) return;
    try {
      const [tpl, resp] = await Promise.all([
        can("clinical.form.read") ? api<Template[]>("/api/v1/clinical-forms/templates") : Promise.resolve([]),
        can("clinical.form.read") ? api<Response[]>(`/api/v1/patients/${patientId}/form-responses`) : Promise.resolve([]),
      ]);
      setTemplates(list<Template>(tpl));
      setResponses(list<Response>(resp));
    } catch (reason) { onError(errorMessage(reason, "Forms could not be loaded.")); }
  }, [patientId, permissions.join(",")]);
  useEffect(() => { void load(); }, [load]);

  const run = async (action: () => Promise<unknown>, success: string) => {
    setBusy(true); setNotice(null);
    try { await action(); setNotice(success); await load(); } catch (reason) { onError(errorMessage(reason, "That change could not be saved.")); } finally { setBusy(false); }
  };

  // ---- builder ----
  const setField = (i: number, patchValue: Partial<Field>) => setDraftFields((fs) => fs.map((f, idx) => idx === i ? { ...f, ...patchValue } : f));
  const saveTemplate = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const name = String(new FormData(event.currentTarget).get("name") ?? "").trim();
    if (!name) return;
    const fields = draftFields.map((f, i) => ({ ...f, key: f.key || slugKey(f.label, i), options: f.type === "select" ? f.options : [] }));
    const form_key = slugKey(name, 0).replace(/_/g, "_");
    void run(() => post("/api/v1/clinical-forms/templates", { form_key, name, field_schema: { fields } }), "Form template created.").then(() => { setShowBuilder(false); setDraftFields([{ key: "field_0", label: "New field", type: "text", required: false, options: [] }]); });
  };
  const archiveTemplate = (t: Template) => void run(() => post(`/api/v1/clinical-forms/templates/${t.id}/status`, { status: "archived", expected_version: t.version }), "Template archived.");

  // ---- fill-in ----
  const startFill = () => {
    const t = templates.find((x) => x.id === fillTemplateId);
    if (!t) return;
    setOpenResponse(null); setAnswers({});
  };
  const coerce = (field: Field, raw: string | boolean): unknown => {
    if (field.type === "checkbox") return Boolean(raw);
    if (field.type === "number") return raw === "" ? undefined : Number(raw);
    return raw === "" ? undefined : raw;
  };
  const clean = (data: Record<string, unknown>) => Object.fromEntries(Object.entries(data).filter(([, v]) => v !== undefined && v !== ""));
  const createDraft = (t: Template) => void run(async () => {
    const created = await post<Response>(`/api/v1/patients/${patientId}/form-responses`, { template_id: t.id, response_data: clean(answers) });
    setOpenResponse(created); setAnswers((created.response_data as Record<string, unknown>) ?? {});
  }, "Draft saved.");
  const updateDraft = (r: Response) => void run(async () => {
    const updated = await patch<Response>(`/api/v1/patients/${patientId}/form-responses/${r.id}`, { expected_version: r.version, response_data: clean(answers) });
    setOpenResponse(updated);
  }, "Draft updated.");
  const submit = (r: Response) => void run(async () => { await post(`/api/v1/patients/${patientId}/form-responses/${r.id}/submit`, { expected_version: r.version }); setOpenResponse(null); setAnswers({}); }, "Form submitted.");
  const reopen = (r: Response) => { const t = templates.find((x) => x.id === r.template_id); setFillTemplateId(t?.id ?? ""); setOpenResponse(r); setAnswers((r.response_data as Record<string, unknown>) ?? {}); };

  const activeTemplate = templates.find((t) => t.id === fillTemplateId) ?? null;
  const editable = !openResponse || openResponse.status === "draft";
  const renderField = (f: Field) => {
    const v = answers[f.key];
    const common = { id: `f_${f.key}`, disabled: !editable, required: f.required };
    if (f.type === "textarea") return <textarea {...common} value={(v as string) ?? ""} onChange={(e) => setAnswers((a) => ({ ...a, [f.key]: e.target.value }))} />;
    if (f.type === "select") return <select {...common} value={(v as string) ?? ""} onChange={(e) => setAnswers((a) => ({ ...a, [f.key]: e.target.value }))}><option value="">Select…</option>{f.options.map((o) => <option key={o}>{o}</option>)}</select>;
    if (f.type === "checkbox") return <input {...common} type="checkbox" checked={Boolean(v)} onChange={(e) => setAnswers((a) => ({ ...a, [f.key]: e.target.checked }))} />;
    const inputType = f.type === "number" ? "number" : f.type === "date" ? "date" : "text";
    return <input {...common} type={inputType} value={(v as string | number) ?? ""} onChange={(e) => setAnswers((a) => ({ ...a, [f.key]: coerce(f, e.target.value) }))} placeholder={f.type === "media_ref" ? "media id" : undefined} />;
  };

  if (!can("clinical.form.read")) return <section className="surface-card"><div className="dashboard-empty"><strong>No access</strong><span>Your role cannot view clinical forms.</span></div></section>;

  return <section className="surface-card">
    <div className="surface-card-heading"><div><p className="eyebrow">SPECIALTY FORMS</p><h2>Structured clinical records.</h2></div>{can("clinical.form.manage") && <button className="button button-primary" onClick={() => setShowBuilder((s) => !s)}>Build form <span>＋</span></button>}</div>
    {notice && <div className="permission-strip" aria-live="polite"><span className="permission-ok">{notice}</span></div>}

    {showBuilder && can("clinical.form.manage") && <form className="manage-form" onSubmit={saveTemplate}>
      <div className="form-grid"><label>Form name<input name="name" required maxLength={160} placeholder="Hair transplant assessment" /></label></div>
      <p className="eyebrow">FIELDS</p>
      {draftFields.map((f, i) => <div className="theme-row" key={i}>
        <input aria-label="Field label" value={f.label} maxLength={160} onChange={(e) => setField(i, { label: e.target.value, key: slugKey(e.target.value, i) })} />
        <select aria-label="Field type" value={f.type} onChange={(e) => setField(i, { type: e.target.value as FieldType, options: e.target.value === "select" && f.options.length === 0 ? ["Option 1"] : f.options })}>{FIELD_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}</select>
        {f.type === "select" && <input aria-label="Options (comma separated)" value={f.options.join(", ")} onChange={(e) => setField(i, { options: e.target.value.split(",").map((o) => o.trim()).filter(Boolean) })} />}
        <label className="inline-check"><input type="checkbox" checked={f.required} onChange={(e) => setField(i, { required: e.target.checked })} /> required</label>
        <button type="button" className="text-control" onClick={() => setDraftFields((fs) => fs.filter((_, idx) => idx !== i))} disabled={draftFields.length <= 1}>Remove</button>
      </div>)}
      <button type="button" className="button button-secondary" onClick={() => setDraftFields((fs) => [...fs, { key: `field_${fs.length}`, label: "New field", type: "text", required: false, options: [] }])} disabled={draftFields.length >= 60}>Add field ＋</button>
      <div className="form-actions"><button className="button button-primary" type="submit" disabled={busy}>Save form</button></div>
    </form>}

    <div className="form-grid"><label>Fill a form<select value={fillTemplateId} onChange={(e) => { setFillTemplateId(e.target.value); setOpenResponse(null); setAnswers({}); }}><option value="">Choose a form…</option>{templates.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</select></label>{fillTemplateId && !openResponse && <div className="form-actions" style={{ alignSelf: "end" }}><button className="button button-secondary" type="button" onClick={startFill} disabled={busy}>New entry</button></div>}</div>

    {activeTemplate && <div className="form-grid">{activeTemplate.field_schema.fields.map((f) => <label key={f.key}>{f.label}{f.required ? " *" : ""}{renderField(f)}</label>)}</div>}
    {activeTemplate && can("clinical.form.manage") && <div className="form-actions" style={{ gap: 8 }}>
      {!openResponse && <button className="button button-primary" type="button" disabled={busy} onClick={() => createDraft(activeTemplate)}>Save draft</button>}
      {openResponse && openResponse.status === "draft" && <>
        <button className="button button-secondary" type="button" disabled={busy} onClick={() => updateDraft(openResponse)}>Update draft</button>
        <button className="button button-primary" type="button" disabled={busy} onClick={() => submit(openResponse)}>Submit</button>
      </>}
      {openResponse && openResponse.status === "submitted" && <span className="pipeline-status status-paid">Submitted — read only</span>}
    </div>}

    <p className="eyebrow" style={{ marginTop: 18 }}>ENTRIES FOR THIS PATIENT</p>
    <div className="invoice-list">{responses.length === 0 && <div className="dashboard-empty"><strong>No form entries yet</strong></div>}{responses.map((r) => <article className="invoice-row" key={r.id}><div className="invoice-mark">{r.form_key.slice(0, 3).toUpperCase()}</div><div className="invoice-main"><h3>{r.name}</h3><small>{new Date(r.updated_at).toLocaleString()} · {Object.keys(r.response_data ?? {}).length} fields</small></div><div className="invoice-actions"><span className={`pipeline-status status-${r.status === "submitted" ? "paid" : "contacted"}`}>{r.status}</span><button className="text-control" onClick={() => reopen(r)}>{r.status === "draft" ? "Open" : "View"}</button></div></article>)}</div>

    {can("clinical.form.manage") && templates.length > 0 && <><p className="eyebrow" style={{ marginTop: 18 }}>TEMPLATES</p><div className="invoice-list">{templates.map((t) => <article className="invoice-row" key={t.id}><div className="invoice-mark">{t.form_key.slice(0, 3).toUpperCase()}</div><div className="invoice-main"><h3>{t.name}</h3><small>{t.field_schema.fields.length} fields · {label(t.status)}</small></div><div className="invoice-actions"><button className="text-control" disabled={busy} onClick={() => archiveTemplate(t)}>Archive</button></div></article>)}</div></>}
  </section>;
}
