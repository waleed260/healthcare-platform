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
const initials = (name: string) => name.split(/\s+/).map((word) => word[0]).join("").slice(0, 3).toUpperCase() || "—";

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
  const submit = (r: Response) => void run(async () => { await post(`/api/v1/patients/${patientId}/form-responses/${r.id}/submit`, { expected_version: r.version }); setOpenResponse(null); setAnswers({}); setFillTemplateId(""); }, "Form submitted.");
  const reopen = (r: Response) => { const t = templates.find((x) => x.id === r.template_id); setFillTemplateId(t?.id ?? ""); setOpenResponse(r); setAnswers((r.response_data as Record<string, unknown>) ?? {}); };

  const activeTemplate = templates.find((t) => t.id === fillTemplateId) ?? null;
  const editable = !openResponse || openResponse.status === "draft";
  const renderField = (f: Field) => {
    const v = answers[f.key];
    const common = { id: `f_${f.key}`, disabled: !editable, required: f.required };
    if (f.type === "textarea") return <textarea {...common} rows={3} value={(v as string) ?? ""} onChange={(e) => setAnswers((a) => ({ ...a, [f.key]: e.target.value }))} />;
    if (f.type === "select") return <select {...common} value={(v as string) ?? ""} onChange={(e) => setAnswers((a) => ({ ...a, [f.key]: e.target.value }))}><option value="">Select…</option>{f.options.map((o) => <option key={o}>{o}</option>)}</select>;
    if (f.type === "checkbox") return <input {...common} type="checkbox" checked={Boolean(v)} onChange={(e) => setAnswers((a) => ({ ...a, [f.key]: e.target.checked }))} />;
    const inputType = f.type === "number" ? "number" : f.type === "date" ? "date" : "text";
    return <input {...common} type={inputType} value={(v as string | number) ?? ""} onChange={(e) => setAnswers((a) => ({ ...a, [f.key]: coerce(f, e.target.value) }))} placeholder={f.type === "media_ref" ? "media id" : undefined} />;
  };

  if (!can("clinical.form.read")) return <section className="surface-card clinical-panel"><div className="clinical-empty"><strong>No access</strong><span>Your role cannot view clinical forms.</span></div></section>;

  return <section className="surface-card clinical-panel">
    <div className="surface-card-heading">
      <div><p className="eyebrow">SPECIALTY FORMS</p><h2>Structured clinical records.</h2>
        <p className="clinical-hint">Build a form once, then fill it for this patient. Submitted entries stay read-only.</p></div>
      {can("clinical.form.manage") && <button className="button button-primary" type="button" onClick={() => setShowBuilder((s) => !s)}>{showBuilder ? "Close builder" : "Build form"} <span>{showBuilder ? "×" : "＋"}</span></button>}
    </div>
    {notice && <div className="permission-strip" aria-live="polite"><span className="permission-ok">{notice}</span></div>}

    {showBuilder && can("clinical.form.manage") && <form className="drawer-form clinical-form" onSubmit={saveTemplate}>
      <label>Form name <span className="drawer-note">required</span>
        <input name="name" required maxLength={160} placeholder="Hair transplant assessment" /></label>
      <div className="clinical-builder-head">
        <p className="drawer-form-section-label">FIELDS</p>
        <span className="clinical-count">{draftFields.length} field{draftFields.length === 1 ? "" : "s"}</span>
      </div>
      <div className="clinical-builder-list">
        {draftFields.map((f, i) => <div className="clinical-builder-row" key={i}>
          <div className="clinical-builder-grid">
            <label>Field label
              <input aria-label="Field label" value={f.label} maxLength={160} onChange={(e) => setField(i, { label: e.target.value, key: slugKey(e.target.value, i) })} /></label>
            <label>Type
              <select aria-label="Field type" value={f.type} onChange={(e) => setField(i, { type: e.target.value as FieldType, options: e.target.value === "select" && f.options.length === 0 ? ["Option 1"] : f.options })}>{FIELD_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}</select></label>
            {f.type === "select" && <label className="clinical-builder-wide">Options
              <input aria-label="Options (comma separated)" value={f.options.join(", ")} placeholder="Option 1, Option 2" onChange={(e) => setField(i, { options: e.target.value.split(",").map((o) => o.trim()).filter(Boolean) })} /></label>}
            <label className="clinical-check"><input type="checkbox" checked={f.required} onChange={(e) => setField(i, { required: e.target.checked })} /> Required</label>
          </div>
          <button type="button" className="text-control danger-control" onClick={() => setDraftFields((fs) => fs.filter((_, idx) => idx !== i))} disabled={draftFields.length <= 1}>Remove field</button>
        </div>)}
      </div>
      <div className="clinical-actions">
        <button type="button" className="button button-secondary" onClick={() => setDraftFields((fs) => [...fs, { key: `field_${fs.length}`, label: "New field", type: "text", required: false, options: [] }])} disabled={draftFields.length >= 60}>Add field <span>＋</span></button>
        <button className="button button-primary" type="submit" disabled={busy}>{busy ? "Saving…" : "Save form"} <span>→</span></button>
      </div>
    </form>}

    <div className="clinical-fill-head">
      <label>Start an entry
        <select value={fillTemplateId} onChange={(e) => { setFillTemplateId(e.target.value); setOpenResponse(null); setAnswers({}); }}>
          <option value="">Choose a form…</option>
          {templates.filter((t) => t.status !== "archived").map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
        </select>
      </label>
      {openResponse && <span className={`pipeline-status status-${openResponse.status === "draft" ? "contacted" : "paid"}`}>{openResponse.status === "draft" ? "Draft open" : "Submitted"}</span>}
    </div>

    {activeTemplate && <div className="drawer-form clinical-fields">
      {activeTemplate.field_schema.fields.map((f) => <label key={f.key}><span className="clinical-field-label">{f.label} <span className="drawer-note">{f.required ? "required" : "optional"}</span></span>
        {renderField(f)}
      </label>)}
    </div>}
    {activeTemplate && can("clinical.form.manage") && <div className="clinical-actions">
      {!openResponse && <button className="button button-primary" type="button" disabled={busy} onClick={() => createDraft(activeTemplate)}>Save draft <span>→</span></button>}
      {openResponse && openResponse.status === "draft" && <>
        <button className="button button-secondary" type="button" disabled={busy} onClick={() => updateDraft(openResponse)}>Update draft</button>
        <button className="button button-primary" type="button" disabled={busy} onClick={() => submit(openResponse)}>Submit <span>→</span></button>
      </>}
      {openResponse && openResponse.status === "submitted" && <span className="pipeline-status status-paid">Submitted — read only</span>}
    </div>}

    <div className="clinical-builder-head">
      <p className="drawer-form-section-label">ENTRIES FOR THIS PATIENT</p>
      {responses.length > 0 && <span className="clinical-count">{responses.length} entr{responses.length === 1 ? "y" : "ies"}</span>}
    </div>
    <div className="clinical-list">
      {responses.length === 0 && <div className="clinical-empty"><strong>No form entries yet</strong><span>Choose a form above and save a draft to start.</span></div>}
      {responses.map((r) => <article className="clinical-row" key={r.id}>
        <div className="clinical-row-mark">{initials(r.name)}</div>
        <div className="clinical-row-main">
          <h3>{r.name}</h3>
          <p>{Object.keys(r.response_data ?? {}).length} fields captured</p>
          <small>{new Date(r.updated_at).toLocaleString()}</small>
        </div>
        <div className="clinical-row-actions">
          <span className={`pipeline-status status-${r.status === "submitted" ? "paid" : "contacted"}`}>{label(r.status)}</span>
          <button className="text-control" type="button" onClick={() => reopen(r)}>{r.status === "draft" ? "Open" : "View"}</button>
        </div>
      </article>)}
    </div>

    {can("clinical.form.manage") && templates.length > 0 && <>
      <div className="clinical-builder-head"><p className="drawer-form-section-label">TEMPLATES</p><span className="clinical-count">{templates.length}</span></div>
      <div className="clinical-list">{templates.map((t) => <article className="clinical-row" key={t.id}>
        <div className="clinical-row-mark">{initials(t.name)}</div>
        <div className="clinical-row-main">
          <h3>{t.name}</h3>
          <p>{t.field_schema.fields.length} fields · {label(t.status)}</p>
        </div>
        <div className="clinical-row-actions">
          <button className="text-control danger-control" type="button" disabled={busy || t.status === "archived"} onClick={() => archiveTemplate(t)}>{t.status === "archived" ? "Archived" : "Archive"}</button>
        </div>
      </article>)}</div>
    </>}
  </section>;
}
