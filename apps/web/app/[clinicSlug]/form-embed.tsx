"use client";

import { FormEvent, useEffect, useState } from "react";
import { buttonClass, inputClass } from "../site-theme";
import type { SiteBrand } from "../site-theme";

type Field = { key: string; label: string; type: string; required: boolean; options: string[] };
type FormDefinition = { id: string; name: string; fields: Field[]; success_message: string };

export default function FormEmbed({ clinicSlug, formId, brand, heading }: { clinicSlug: string; formId: string; brand: SiteBrand; heading?: string }) {
  const [form, setForm] = useState<FormDefinition | null>(null);
  const [answers, setAnswers] = useState<Record<string, string | boolean>>({});
  const [state, setState] = useState<"loading" | "ready" | "sending" | "sent" | "missing">("loading");
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void fetch(`/api/v1/public/sites/slug/${encodeURIComponent(clinicSlug)}/forms/${encodeURIComponent(formId)}`, { cache: "no-store" })
      .then(async (response) => { if (!response.ok) throw new Error("missing"); const payload = await response.json(); if (active) { setForm(payload.data as FormDefinition); setState("ready"); } })
      .catch(() => { if (active) setState("missing"); });
    return () => { active = false; };
  }, [clinicSlug, formId]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!form) return;
    setState("sending"); setMessage(null);
    try {
      const response = await fetch(`/api/v1/public/sites/slug/${encodeURIComponent(clinicSlug)}/forms/${encodeURIComponent(formId)}/submit`, { method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() }, body: JSON.stringify({ answers }) });
      const payload = await response.json() as { data?: { message?: string }; error?: { message?: string } };
      if (!response.ok) throw new Error(payload.error?.message ?? "We could not send your message.");
      setMessage(payload.data?.message ?? form.success_message); setState("sent");
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "We could not send your message."); setState("ready");
    }
  }

  if (state === "missing") return null;
  if (state === "loading" || !form) return <p role="status">Loading form…</p>;
  if (state === "sent") return <div className="public-lead-success" role="status"><strong>{message}</strong></div>;
  const set = (key: string, value: string | boolean) => setAnswers((current) => ({ ...current, [key]: value }));
  return <section className="public-section" id={`form-${form.id}`}><div className="public-section-heading"><h2>{heading || form.name}</h2></div>
    <form className={`public-form ${inputClass(brand)}`} onSubmit={submit}>
      {form.fields.map((field) => field.type === "consent" || field.type === "checkbox"
        ? <label key={field.key} className="inline-check"><input type="checkbox" required={field.required} checked={answers[field.key] === true} onChange={(event) => set(field.key, event.target.checked)} /> {field.label}</label>
        : <label key={field.key}>{field.label}{field.required ? " *" : ""}
          {field.type === "textarea" ? <textarea rows={4} maxLength={2000} required={field.required} onChange={(event) => set(field.key, event.target.value)} />
            : field.type === "dropdown" ? <select required={field.required} defaultValue="" onChange={(event) => set(field.key, event.target.value)}><option value="">Select…</option>{field.options.map((option) => <option key={option}>{option}</option>)}</select>
            : <input type={field.type === "email" ? "email" : field.type === "phone" ? "tel" : field.type === "date" ? "date" : "text"} maxLength={320} required={field.required} onChange={(event) => set(field.key, event.target.value)} />}</label>)}
      {message && <p role="alert">{message}</p>}
      <button className={`button button-primary ${buttonClass(brand)}`} type="submit" disabled={state === "sending"}>{state === "sending" ? "Sending…" : "Send"} <span>→</span></button>
    </form></section>;
}
