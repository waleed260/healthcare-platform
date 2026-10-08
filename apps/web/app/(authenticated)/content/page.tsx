"use client";

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import anime from "animejs";
import { api, errorMessage, label, patch, post } from "../_lib/client";
import { useToast } from "../_lib/toast";
import { useConfirm } from "../_lib/confirm";

type Field = { key: string; label: string; type: string; required: boolean; options: string[]; maps_to: string | null };
type Form = { id: string; name: string; fields: Field[]; action: string; status: string; version: number; success_message: string };
type Post = { id: string; slug: string; title: string; excerpt: string; body: string; status: string; version: number; updated_at: string; seo_title: string; seo_description: string; canonical_url: string };
type Testimonial = { id: string; author_name: string; rating: number; body: string; status: string; version: number; display_name: string; show_rating: boolean };
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
  const [search, setSearch] = useState("");
  const toast = useToast();
  const confirm = useConfirm();
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
    setBusy(true); setError(null);
    try { await action(); toast.success(success); setShowForm(false); setEditingPost(null); await load(); } catch (reason) { toast.error(errorMessage(reason, "That change could not be saved.")); } finally { setBusy(false); }
  };

  const filteredPosts = useMemo(() => {
    if (!search) return posts;
    const q = search.toLowerCase();
    return posts.filter((p) => p.title.toLowerCase().includes(q) || p.slug.toLowerCase().includes(q));
  }, [posts, search]);

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
    const body = { title: String(data.get("title")).trim(), excerpt: String(data.get("excerpt")).trim(), body: String(data.get("body")), seo_title: String(data.get("seo_title") ?? "").trim() || undefined, seo_description: String(data.get("seo_description") ?? "").trim() || undefined, canonical_url: String(data.get("canonical_url") ?? "").trim() || undefined };
    void run(() => editingPost ? patch(`/api/v1/website-content/posts/${editingPost.id}`, { expected_version: editingPost.version, ...body }) : post("/api/v1/website-content/posts", { slug: slugify(body.title) || "post", ...body }), editingPost ? "Post saved." : "Draft created.");
  };
  const setPostStatus = async (item: Post, next: string) => {
    if (next === "published") {
      const ok = await confirm({ title: "Publish post", message: `"${item.title}" will be visible on your website.`, confirmLabel: "Publish" });
      if (!ok) return;
    }
    void run(() => post(`/api/v1/website-content/posts/${item.id}/status`, { expected_version: item.version, status: next }), `Post ${next}.`);
  };
  const saveTestimonial = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const target = event.currentTarget;
    void run(async () => { await post("/api/v1/website-content/testimonials", { author_name: String(data.get("author")).trim(), rating: Number(data.get("rating")), body: String(data.get("body")).trim(), display_name: String(data.get("display_name")), show_rating: data.get("show_rating") === "on", consent_confirmed: data.get("consent") === "on" }); target.reset(); }, "Testimonial added for review.");
  };
  const moderate = async (item: Testimonial, next: string) => {
    if (next === "rejected") {
      const ok = await confirm({ message: `Reject this testimonial from ${item.author_name}?`, danger: true, confirmLabel: "Reject" });
      if (!ok) return;
    }
    void run(() => post(`/api/v1/website-content/testimonials/${item.id}/moderate`, { expected_version: item.version, status: next }), `Testimonial ${next}.`);
  };
  const updateField = (index: number, patchValue: Partial<Field>) => setDraftFields((fields) => fields.map((field, i) => i === index ? { ...field, ...patchValue } : field));
  const [dragFieldIndex, setDragFieldIndex] = useState<number | null>(null);
  const dropField = (targetIndex: number) => {
    if (dragFieldIndex === null || dragFieldIndex === targetIndex) return;
    setDraftFields((fields) => {
      const next = [...fields];
      const [moved] = next.splice(dragFieldIndex, 1);
      next.splice(targetIndex, 0, moved);
      return next;
    });
    setDragFieldIndex(null);
  };

  const contentRef = useRef<HTMLElement>(null);
  useEffect(() => {
    if (!contentRef.current) return;
    anime({ targets: contentRef.current.querySelectorAll(".surface-card, .inventory-summary > div"), opacity: [0, 1], translateY: [22, 0], duration: 500, delay: anime.stagger(50, { start: 120 }), easing: "easeOutCubic" });
  }, [tab]);

  return <main className="workspace-page content-page" ref={contentRef}>
    <div className="workspace-page-header"><div><p className="eyebrow">WEBSITE · CONTENT</p><h1>Words and <em>forms</em> that work.</h1><p className="workspace-page-intro">Build lead and appointment-request forms, publish blog articles, and approve testimonials before they appear on your site.</p></div></div>
    {error && <div className="workspace-alert" role="alert"><strong>{error}</strong><button className="ghost-button" onClick={() => void load()}>Try again <span>→</span></button></div>}

    <div className="inventory-summary" style={{ marginBottom: 20 }}>
      <div><span className="eyebrow">FORMS</span><strong>{forms.length}</strong><small>lead capture forms</small></div>
      <div><span className="eyebrow">POSTS</span><strong>{posts.length}</strong><small>{posts.filter((p) => p.status === "published").length} published</small></div>
      <div><span className="eyebrow">TESTIMONIALS</span><strong>{testimonials.length}</strong><small>{testimonials.filter((t) => t.status === "pending").length} pending review</small></div>
    </div>

    <div className="pipeline-toolbar"><div className="pipeline-tabs" role="tablist">{TABS.map((item) => <button key={item} role="tab" aria-selected={tab === item} className={tab === item ? "active" : ""} onClick={() => { setTab(item); setShowForm(false); setEditingPost(null); setSearch(""); }}>{label(item)}{item === "testimonials" && testimonials.filter((t) => t.status === "pending").length > 0 ? ` (${testimonials.filter((t) => t.status === "pending").length})` : ""}</button>)}</div></div>

    {tab === "forms" && <section className="surface-card"><div className="surface-card-heading"><div><p className="eyebrow">FORM BUILDER</p><h2>Capture leads and requests.</h2></div>{can("website.edit") && <button className="button button-primary" onClick={() => setShowForm((value) => !value)}>New form <span>＋</span></button>}</div>
      {showForm && <form className="manage-form" onSubmit={saveForm}><div className="form-grid"><label>Name<input name="name" required maxLength={120} placeholder="Appointment request" /></label><label>Action<select name="action"><option value="lead">Create a lead</option><option value="appointment_request">Appointment request (lead, flagged)</option></select></label><label>Thank-you message<input name="success" maxLength={300} /></label></div>
        <p className="eyebrow">FIELDS</p>{draftFields.map((field, index) => <div className="theme-row" key={index} draggable onDragStart={() => setDragFieldIndex(index)} onDragOver={(e) => e.preventDefault()} onDrop={() => dropField(index)} style={dragFieldIndex === index ? { opacity: 0.5 } : undefined}><span className="drag-handle" aria-label="Drag to reorder" style={{ cursor: "grab", userSelect: "none", marginRight: 6 }}>⠿</span><input aria-label="Label" value={field.label} maxLength={120} onChange={(event) => updateField(index, { label: event.target.value, key: field.key })} /><select aria-label="Type" value={field.type} onChange={(event) => updateField(index, { type: event.target.value, options: event.target.value === "dropdown" && field.options.length === 0 ? ["Option 1"] : field.options })}>{FIELD_TYPES.map((type) => <option key={type}>{type}</option>)}</select>{field.type === "dropdown" && <input aria-label="Options (comma separated)" value={field.options.join(", ")} onChange={(event) => updateField(index, { options: event.target.value.split(",").map((option) => option.trim()).filter(Boolean) })} />}<label className="inline-check"><input type="checkbox" checked={field.required} disabled={field.type === "consent"} onChange={(event) => updateField(index, { required: event.target.checked })} /> required</label><button type="button" className="text-control" disabled={Boolean(field.maps_to) || field.type === "consent"} onClick={() => setDraftFields((fields) => fields.filter((_, i) => i !== index))}>Remove</button></div>)}
        <button type="button" className="button button-secondary" onClick={() => setDraftFields((fields) => [...fields.slice(0, -1), { key: `field_${fields.length}`, label: "New field", type: "text", required: false, options: [], maps_to: null }, fields[fields.length - 1]])} disabled={draftFields.length >= 25}>Add field ＋</button>
        <div className="form-actions"><button className="button button-primary" type="submit" disabled={busy}>Save form</button></div></form>}
      <div className="invoice-list">{forms.length === 0 && <div className="dashboard-empty"><strong>No forms yet</strong><span>Create one, then add it to a page.</span></div>}{forms.map((form) => <article className="invoice-row" key={form.id}><div className="invoice-mark">FRM</div><div className="invoice-main"><h3>{form.name}</h3><p>{form.fields.length} fields · {label(form.action)}</p><small>{form.id}</small></div><div className="invoice-actions"><span className={`pipeline-status status-${form.status === "active" ? "paid" : "void"}`}>{form.status}</span>{can("website.edit") && pages.length > 0 && <select aria-label={`Add ${form.name} to page`} defaultValue="" disabled={busy} onChange={(event) => { if (event.target.value) addToPage(form, event.target.value); event.target.value = ""; }}><option value="">Add to page…</option>{pages.map((page) => <option key={page.id} value={page.id}>{page.title}</option>)}</select>}{can("website.edit") && <button className="text-control" disabled={busy} onClick={() => void run(() => patch(`/api/v1/website-content/forms/${form.id}`, { expected_version: form.version, status: form.status === "active" ? "archived" : "active" }), "Form updated.")}>{form.status === "active" ? "Archive" : "Restore"}</button>}</div></article>)}</div></section>}

    {tab === "blog" && <section className="surface-card"><div className="surface-card-heading"><div><p className="eyebrow">BLOG</p><h2>Share what you know.</h2></div><div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        {posts.length > 3 && <input type="search" placeholder="Search posts…" value={search} onChange={(e) => setSearch(e.target.value)} style={{ maxWidth: 200, padding: "6px 12px", border: "1px solid var(--border-subtle, #e5e5e3)", borderRadius: 6, fontSize: "0.85rem", background: "var(--surface-1, #fff)" }} />}
        {can("website.edit") && <button className="button button-primary" onClick={() => { setEditingPost(null); setShowForm((value) => !value); }}>New post <span>＋</span></button>}
      </div></div>
      {(showForm || editingPost) && <form className="manage-form" key={editingPost?.id ?? "new"} onSubmit={savePost}><div className="form-grid"><label>Title<input name="title" required maxLength={200} defaultValue={editingPost?.title ?? ""} /></label><label>Summary<input name="excerpt" maxLength={400} defaultValue={editingPost?.excerpt ?? ""} /></label></div><label className="font-field">Article (basic HTML allowed)<textarea name="body" rows={10} maxLength={50000} defaultValue={editingPost?.body ?? ""} /></label>
        <details className="seo-details" style={{ marginTop: 12 }}><summary style={{ cursor: "pointer", fontSize: "0.85rem", fontWeight: 600, color: "var(--text-2, #666)" }}>SEO settings</summary><div className="form-grid" style={{ marginTop: 8 }}><label>SEO title<input name="seo_title" maxLength={70} placeholder={editingPost?.title ?? "Defaults to post title"} defaultValue={editingPost?.seo_title ?? ""} /></label><label>Meta description<input name="seo_description" maxLength={160} placeholder="Brief summary for search engines" defaultValue={editingPost?.seo_description ?? ""} /></label><label>Canonical URL<input name="canonical_url" type="url" maxLength={500} placeholder="https://…" defaultValue={editingPost?.canonical_url ?? ""} /></label></div></details>
        <div className="form-actions"><button className="button button-secondary" type="button" onClick={() => { setShowForm(false); setEditingPost(null); }}>Cancel</button><button className="button button-primary" type="submit" disabled={busy}>{busy ? "Saving…" : editingPost ? "Update post" : "Save draft"}</button></div></form>}
      <div className="invoice-list">{filteredPosts.length === 0 && <div className="dashboard-empty"><strong>{search ? "No matching posts" : "No posts yet"}</strong><span>{search ? "Try a different search term." : "Write your first article to share expertise with patients."}</span></div>}{filteredPosts.map((item) => <article className="invoice-row" key={item.id}><div className="invoice-mark">BLG</div><div className="invoice-main"><h3>{item.title}</h3><p>/blog/{item.slug}</p><small>{item.excerpt || "No summary"} · Updated {new Date(item.updated_at).toLocaleDateString()}</small></div><div className="invoice-actions"><span className={`pipeline-status status-${item.status === "published" ? "paid" : "contacted"}`}>{item.status}</span><span className="receipt-links">{can("website.edit") && <button className="text-control" onClick={() => { setShowForm(false); setEditingPost(item); }}>Edit</button>}{can("website.publish") && (item.status === "published" ? <button className="text-control" disabled={busy} onClick={() => void setPostStatus(item, "draft")}>Unpublish</button> : <button className="text-control" disabled={busy} onClick={() => void setPostStatus(item, "published")}>Publish</button>)}</span></div></article>)}</div></section>}

    {tab === "testimonials" && <section className="surface-card"><div className="surface-card-heading"><div><p className="eyebrow">TESTIMONIALS</p><h2>Approved reviews only.</h2></div></div>
      {can("website.edit") && <form className="manage-form" onSubmit={saveTestimonial}><div className="form-grid"><label>Author<input name="author" required maxLength={120} placeholder="First name and initial" /></label><label>Rating<select name="rating" defaultValue="5">{[5, 4, 3, 2, 1].map((value) => <option key={value}>{value}</option>)}</select></label><label>Testimonial<input name="body" required maxLength={1500} /></label><label>Display name as<select name="display_name" defaultValue="full"><option value="full">Full name</option><option value="initials">Initials only</option><option value="anonymous">Anonymous</option></select></label><label className="inline-check"><input type="checkbox" name="show_rating" defaultChecked /> Show star rating on site</label><label className="inline-check"><input type="checkbox" name="consent" required /> The author consented to publication</label></div><div className="form-actions"><button className="button button-secondary" type="submit" disabled={busy}>Add for review</button></div></form>}
      <div className="invoice-list">{testimonials.length === 0 && <div className="dashboard-empty"><strong>No testimonials yet</strong></div>}{testimonials.map((item) => { const displayAuthor = item.display_name === "anonymous" ? "Anonymous" : item.display_name === "initials" ? item.author_name.split(/\s+/).map((w) => w[0]).join("").toUpperCase() : item.author_name; return <article className="invoice-row" key={item.id}><div className="invoice-mark">{item.show_rating !== false ? "★".repeat(item.rating).slice(0, 3) : "···"}</div><div className="invoice-main"><h3>{displayAuthor} · {item.rating}/5</h3><p>{item.body}</p><small>{item.display_name === "full" || !item.display_name ? "Full name" : item.display_name === "initials" ? "Initials only" : "Anonymous"}{item.show_rating === false ? " · Rating hidden" : ""}</small></div><div className="invoice-actions"><span className={`pipeline-status status-${item.status === "approved" ? "paid" : item.status === "pending" ? "contacted" : "void"}`}>{item.status}</span>{can("website.publish") && <span className="receipt-links">{item.status !== "approved" && <button className="text-control" disabled={busy} onClick={() => moderate(item, "approved")}>Approve</button>}{item.status !== "rejected" && <button className="text-control" disabled={busy} onClick={() => moderate(item, "rejected")}>Reject</button>}</span>}</div></article>; })}</div></section>}
  </main>;
}
