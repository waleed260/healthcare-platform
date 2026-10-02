"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, errorMessage, label, patch, post } from "../_lib/client";

type Field = { key: string; label: string; type: string; required: boolean; options: string[]; maps_to: string | null };
type Form = { id: string; name: string; fields: Field[]; action: string; status: string; version: number; success_message: string };
type Post = { id: string; slug: string; title: string; excerpt: string; body: string; status: string; version: number; updated_at: string };
type Testimonial = { id: string; author_name: string; rating: number; body: string; status: string; version: number };
type Website = { id: string };
type Page = { id: string; slug: string; title: string };
type Session = { permissions?: string[] };

const TABS = ["forms", "blog", "testimonials"] as const;
type Tab = (typeof TABS)[number];
const FIELD_TYPES = ["text", "textarea", "phone", "email", "dropdown", "checkbox", "date", "consent"];
const DEFAULT_FIELDS: Field[] = [
  { key: "name", label: "Full name", type: "text", required: true, options: [], maps_to: "full_name" },
  { key: "phone", label: "Phone", type: "phone", required: true, options: [], maps_to: "phone" },
  { key: "email", label: "Email", type: "email", required: false, options: [], maps_to: "email" },
  { key: "message", label: "How can we help?", type: "textarea", required: false, options: [], maps_to: "notes" },
  { key: "consent", label: "I agree to be contacted about my enquiry", type: "consent", required: true, options: [], maps_to: null },
];
const slugify = (value: string) => value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 120);

export default function ContentPage() {
  const [tab, setTab] = useState<Tab>("forms");
  const [permissions, setPermissions] = useState<string[]>([]);
  const [forms, setForms] = useState<Form[]>([]);
  const [posts, setPosts] = useState<Post[]>([]);
  const [testimonials, setTestimonials] = useState<Testimonial[]>([]);
  const [pages, setPages] = useState<Page[]>([]);
  const [website, setWebsite] = useState<Website | null>(null);
  const [draftFields, setDraftFields] = useState<Field[]>(DEFAULT_FIELDS);
  const [editingPost, setEditingPost] = useState<Post | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const can = (permission: string) => permissions.includes(permission);

  const load = useCallback(async () => {
    setError(null);
    try {
      const session = await api<Session>("/api/v1/auth/me");
      setPermissions(session.permissions ?? []);
      const [formRows, postRows, testimonialRows, sites] = await Promise.all([
        api<Form[]>("/api/v1/website-content/forms"), api<Post[]>("/api/v1/website-content/posts"),
        api<Testimonial[]>("/api/v1/website-content/testimonials"), api<Website[]>("/api/v1/websites"),
      ]);
      setForms(Array.isArray(formRows) ? formRows : []); setPosts(Array.isArray(postRows) ? postRows : []); setTestimonials(Array.isArray(testimonialRows) ? testimonialRows : []);
      const first = Array.isArray(sites) ? sites[0] ?? null : null;
      setWebsite(first);
      setPages(first ? (await api<Page[]>(`/api/v1/websites/${first.id}/pages?limit=100`)) ?? [] : []);
    } catch (reason) { setError(errorMessage(reason, "Content could not be loaded.")); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const run = async (action: () => Promise<unknown>, success: string) => {
    setBusy(true); setError(null); setNotice(null);
    try { await action(); setNotice(success); setShowForm(false); setEditingPost(null); await load(); } catch (reason) { setError(errorMessage(reason, "That change could not be saved.")); } finally { setBusy(false); }
  };

  const saveForm = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    void run(() => post("/api/v1/website-content/forms", { name: String(data.get("name")).trim(), action: data.get("action"), success_message: String(data.get("success")).trim() || "Thanks, we will be in touch shortly.", fields: draftFields.map((field) => ({ ...field, options: field.type === "dropdown" ? field.options : [] })) }), "Form created.");
  };
  const addToPage = (form: Form, pageId: string) => {
    if (!website || !pageId) return;
    void run(() => post(`/api/v1/websites/${website.id}/pages/${pageId}/sections`, { section_type: "lead_form", layout_key: "form", position: 50, content: { heading: form.name, body: "", items: [{ form_id: form.id }] }, is_visible: true }), "Form added to the page draft.");
  };
  const savePost = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const body = { title: String(data.get("title")).trim(), excerpt: String(data.get("excerpt")).trim(), body: String(data.get("body")) };
    void run(() => editingPost ? patch(`/api/v1/website-content/posts/${editingPost.id}`, { expected_version: editingPost.version, ...body }) : post("/api/v1/website-content/posts", { slug: slugify(body.title) || "post", ...body }), editingPost ? "Post saved." : "Draft created.");
  };
  const setPostStatus = (item: Post, next: string) => void run(() => post(`/api/v1/website-content/posts/${item.id}/status`, { expected_version: item.version, status: next }), `Post ${next}.`);
  const saveTestimonial = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const target = event.currentTarget;
    void run(async () => { await post("/api/v1/website-content/testimonials", { author_name: String(data.get("author")).trim(), rating: Number(data.get("rating")), body: String(data.get("body")).trim(), consent_confirmed: data.get("consent") === "on" }); target.reset(); }, "Testimonial added for review.");
  };
  const moderate = (item: Testimonial, next: string) => void run(() => post(`/api/v1/website-content/testimonials/${item.id}/moderate`, { expected_version: item.version, status: next }), `Testimonial ${next}.`);
  const updateField = (index: number, patchValue: Partial<Field>) => setDraftFields((fields) => fields.map((field, i) => i === index ? { ...field, ...patchValue } : field));

  return <main className="workspace-page content-page">
    <div className="workspace-page-header"><div><p className="eyebrow">WEBSITE · CONTENT</p><h1>Words and <em>forms</em> that work.</h1><p className="workspace-page-intro">Build lead and appointment-request forms, publish blog articles, and approve testimonials before they appear on your site.</p></div></div>
    {error && <div className="workspace-alert" role="alert"><strong>{error}</strong></div>}
    {notice && <div className="permission-strip" aria-live="polite"><span className="permission-ok">{notice}</span></div>}
    <div className="pipeline-toolbar"><div className="pipeline-tabs" role="tablist">{TABS.map((item) => <button key={item} role="tab" aria-selected={tab === item} className={tab === item ? "active" : ""} onClick={() => { setTab(item); setShowForm(false); setEditingPost(null); }}>{label(item)}</button>)}</div></div>

    {tab === "forms" && <section className="surface-card"><div className="surface-card-heading"><div><p className="eyebrow">FORM BUILDER</p><h2>Capture leads and requests.</h2></div>{can("website.edit") && <button className="button button-primary" onClick={() => setShowForm((value) => !value)}>New form <span>＋</span></button>}</div>
      {showForm && <form className="manage-form" onSubmit={saveForm}><div className="form-grid"><label>Name<input name="name" required maxLength={120} placeholder="Appointment request" /></label><label>Action<select name="action"><option value="lead">Create a lead</option><option value="appointment_request">Appointment request (lead, flagged)</option></select></label><label>Thank-you message<input name="success" maxLength={300} /></label></div>
        <p className="eyebrow">FIELDS</p>{draftFields.map((field, index) => <div className="theme-row" key={index}><input aria-label="Label" value={field.label} maxLength={120} onChange={(event) => updateField(index, { label: event.target.value, key: field.key })} /><select aria-label="Type" value={field.type} onChange={(event) => updateField(index, { type: event.target.value, options: event.target.value === "dropdown" && field.options.length === 0 ? ["Option 1"] : field.options })}>{FIELD_TYPES.map((type) => <option key={type}>{type}</option>)}</select>{field.type === "dropdown" && <input aria-label="Options (comma separated)" value={field.options.join(", ")} onChange={(event) => updateField(index, { options: event.target.value.split(",").map((option) => option.trim()).filter(Boolean) })} />}<label className="inline-check"><input type="checkbox" checked={field.required} disabled={field.type === "consent"} onChange={(event) => updateField(index, { required: event.target.checked })} /> required</label><button type="button" className="text-control" disabled={Boolean(field.maps_to) || field.type === "consent"} onClick={() => setDraftFields((fields) => fields.filter((_, i) => i !== index))}>Remove</button></div>)}
        <button type="button" className="button button-secondary" onClick={() => setDraftFields((fields) => [...fields.slice(0, -1), { key: `field_${fields.length}`, label: "New field", type: "text", required: false, options: [], maps_to: null }, fields[fields.length - 1]])} disabled={draftFields.length >= 25}>Add field ＋</button>
        <div className="form-actions"><button className="button button-primary" type="submit" disabled={busy}>Save form</button></div></form>}
      <div className="invoice-list">{forms.length === 0 && <div className="dashboard-empty"><strong>No forms yet</strong><span>Create one, then add it to a page.</span></div>}{forms.map((form) => <article className="invoice-row" key={form.id}><div className="invoice-mark">FRM</div><div className="invoice-main"><h3>{form.name}</h3><p>{form.fields.length} fields · {label(form.action)}</p><small>{form.id}</small></div><div className="invoice-actions"><span className={`pipeline-status status-${form.status === "active" ? "paid" : "void"}`}>{form.status}</span>{can("website.edit") && pages.length > 0 && <select aria-label={`Add ${form.name} to page`} defaultValue="" disabled={busy} onChange={(event) => { if (event.target.value) addToPage(form, event.target.value); event.target.value = ""; }}><option value="">Add to page…</option>{pages.map((page) => <option key={page.id} value={page.id}>{page.title}</option>)}</select>}{can("website.edit") && <button className="text-control" disabled={busy} onClick={() => void run(() => patch(`/api/v1/website-content/forms/${form.id}`, { expected_version: form.version, status: form.status === "active" ? "archived" : "active" }), "Form updated.")}>{form.status === "active" ? "Archive" : "Restore"}</button>}</div></article>)}</div></section>}

    {tab === "blog" && <section className="surface-card"><div className="surface-card-heading"><div><p className="eyebrow">BLOG</p><h2>Share what you know.</h2></div>{can("website.edit") && <button className="button button-primary" onClick={() => { setEditingPost(null); setShowForm((value) => !value); }}>New post <span>＋</span></button>}</div>
      {(showForm || editingPost) && <form className="manage-form" key={editingPost?.id ?? "new"} onSubmit={savePost}><div className="form-grid"><label>Title<input name="title" required maxLength={200} defaultValue={editingPost?.title ?? ""} /></label><label>Summary<input name="excerpt" maxLength={400} defaultValue={editingPost?.excerpt ?? ""} /></label></div><label className="font-field">Article (basic HTML allowed)<textarea name="body" rows={10} maxLength={50000} defaultValue={editingPost?.body ?? ""} /></label><div className="form-actions"><button className="button button-primary" type="submit" disabled={busy}>Save</button></div></form>}
      <div className="invoice-list">{posts.length === 0 && <div className="dashboard-empty"><strong>No posts yet</strong></div>}{posts.map((item) => <article className="invoice-row" key={item.id}><div className="invoice-mark">BLG</div><div className="invoice-main"><h3>{item.title}</h3><p>/blog/{item.slug}</p><small>{item.excerpt}</small></div><div className="invoice-actions"><span className={`pipeline-status status-${item.status === "published" ? "paid" : "contacted"}`}>{item.status}</span><span className="receipt-links">{can("website.edit") && <button className="text-control" onClick={() => { setShowForm(false); setEditingPost(item); }}>Edit</button>}{can("website.publish") && (item.status === "published" ? <button className="text-control" disabled={busy} onClick={() => setPostStatus(item, "draft")}>Unpublish</button> : <button className="text-control" disabled={busy} onClick={() => setPostStatus(item, "published")}>Publish</button>)}</span></div></article>)}</div></section>}

    {tab === "testimonials" && <section className="surface-card"><div className="surface-card-heading"><div><p className="eyebrow">TESTIMONIALS</p><h2>Approved reviews only.</h2></div></div>
      {can("website.edit") && <form className="manage-form" onSubmit={saveTestimonial}><div className="form-grid"><label>Author<input name="author" required maxLength={120} placeholder="First name and initial" /></label><label>Rating<select name="rating" defaultValue="5">{[5, 4, 3, 2, 1].map((value) => <option key={value}>{value}</option>)}</select></label><label>Testimonial<input name="body" required maxLength={1500} /></label><label className="inline-check"><input type="checkbox" name="consent" required /> The author consented to publication</label></div><div className="form-actions"><button className="button button-secondary" type="submit" disabled={busy}>Add for review</button></div></form>}
      <div className="invoice-list">{testimonials.length === 0 && <div className="dashboard-empty"><strong>No testimonials yet</strong></div>}{testimonials.map((item) => <article className="invoice-row" key={item.id}><div className="invoice-mark">{"★".repeat(item.rating).slice(0, 3)}</div><div className="invoice-main"><h3>{item.author_name} · {item.rating}/5</h3><p>{item.body}</p></div><div className="invoice-actions"><span className={`pipeline-status status-${item.status === "approved" ? "paid" : item.status === "pending" ? "contacted" : "void"}`}>{item.status}</span>{can("website.publish") && <span className="receipt-links">{item.status !== "approved" && <button className="text-control" disabled={busy} onClick={() => moderate(item, "approved")}>Approve</button>}{item.status !== "rejected" && <button className="text-control" disabled={busy} onClick={() => moderate(item, "rejected")}>Reject</button>}</span>}</div></article>)}</div></section>}
  </main>;
}
