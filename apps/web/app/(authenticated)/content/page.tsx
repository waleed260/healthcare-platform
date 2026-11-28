"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
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
const displayName = (item: Testimonial) => item.display_name === "anonymous" ? "Anonymous" : item.display_name === "initials" ? item.author_name.split(/\s+/).map((word) => word[0]).join("").toUpperCase() : item.author_name;

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
  const [dragFieldIndex, setDragFieldIndex] = useState<number | null>(null);
  const toast = useToast();
  const confirm = useConfirm();
  const can = (permission: string) => permissions.includes(permission);

  const load = useCallback(async () => {
    setError(null);
    try {
      const session = await api<Session>("/api/v1/auth/me");
      setPermissions(session.permissions ?? []);
      const results = await Promise.allSettled([
        api<Form[]>("/api/v1/website-content/forms"), api<Post[]>("/api/v1/website-content/posts"),
        api<Testimonial[]>("/api/v1/website-content/testimonials"), api<Website[]>("/api/v1/websites"),
      ]);
      const val = <T,>(r: PromiseSettledResult<T | null>, fallback: T): T => r.status === "fulfilled" ? (r.value ?? fallback) : fallback;
      setForms(val(results[0], []) as Form[]); setPosts(val(results[1], []) as Post[]); setTestimonials(val(results[2], []) as Testimonial[]);
      const sites = val(results[3], []) as Website[];
      const first = Array.isArray(sites) ? sites[0] ?? null : null;
      setWebsite(first);
      setPages(first ? (await api<Page[]>(`/api/v1/websites/${first.id}/pages?limit=100`)) ?? [] : []);
      const failed = results.filter((r) => r.status === "rejected");
      if (failed.length === results.length) {
        setError(errorMessage((failed[0] as PromiseRejectedResult).reason, "Content could not be loaded."));
      } else if (failed.length > 0) {
        setError(`${failed.length} of ${results.length} content sections could not be loaded.`);
      }
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
  const addField = () => setDraftFields((fields) => [...fields.slice(0, -1), { key: `field_${fields.length}`, label: "New field", type: "text", required: false, options: [], maps_to: null }, fields[fields.length - 1]]);
  const toggleTab = (next: Tab) => { setTab(next); setShowForm(false); setEditingPost(null); setSearch(""); };
  const pendingReviews = testimonials.filter((item) => item.status === "pending").length;

  return <main className="workspace-page content-page">
    <div className="workspace-page-header"><div><p className="eyebrow">WEBSITE · CONTENT</p><h1>Words and <em>forms</em> that work.</h1><p className="workspace-page-intro">Build lead and appointment-request forms, publish blog articles, and approve testimonials before they appear on your site.</p></div></div>
    {error && <div className="workspace-alert" role="alert"><strong>{error}</strong><button className="ghost-button" onClick={() => void load()}>Try again <span>→</span></button></div>}

    <div className="inventory-summary" style={{ marginBottom: 20 }}>
      <div><span className="eyebrow">FORMS</span><strong>{forms.length}</strong><small>lead capture forms</small></div>
      <div><span className="eyebrow">POSTS</span><strong>{posts.length}</strong><small>{posts.filter((p) => p.status === "published").length} published</small></div>
      <div><span className="eyebrow">TESTIMONIALS</span><strong>{testimonials.length}</strong><small>{pendingReviews} pending review</small></div>
    </div>

    <div className="pipeline-toolbar"><div className="pipeline-tabs" role="tablist">{TABS.map((item) => <button key={item} role="tab" aria-selected={tab === item} className={tab === item ? "active" : ""} onClick={() => toggleTab(item)}>{label(item)}{item === "testimonials" && pendingReviews > 0 ? ` (${pendingReviews})` : ""}</button>)}</div></div>

    {tab === "forms" && <section className="surface-card">
      <div className="surface-card-heading"><div><p className="eyebrow">FORM BUILDER</p><h2>Capture leads and requests.</h2></div>{can("website.edit") && <button className="button button-primary" onClick={() => setShowForm((value) => !value)}>{showForm ? "Close" : "New form"} <span>{showForm ? "×" : "＋"}</span></button>}</div>

      {showForm && <form className="content-form" onSubmit={saveForm}>
        <div className="content-form-head">
          <div>
            <p className="eyebrow">NEW FORM</p>
            <h3>Build a form for your site.</h3>
            <p>Choose what to ask, reorder the fields, and pick where each answer lands in your CRM.</p>
          </div>
          <span className="content-form-badge">Draft</span>
        </div>

        <div className="content-form-body">
          <div className="form-grid">
            <label><span className="field-label">Form name <em>up to 120 characters</em></span><input name="name" required maxLength={120} placeholder="Appointment request" /></label>
            <label><span className="field-label">What it creates</span><select name="action"><option value="lead">Create a lead</option><option value="appointment_request">Appointment request (lead, flagged)</option></select></label>
            <label className="field-wide"><span className="field-label">Thank-you message <em>up to 300 characters</em></span><input name="success" maxLength={300} placeholder="Thanks, we will be in touch shortly." /></label>
          </div>

          <div className="form-section">
            <div className="form-section-head"><p className="eyebrow">Fields</p><span>{draftFields.length} of 25 · drag ⠿ to reorder</span></div>
            <div className="field-table">
              <div className="field-table-head" aria-hidden="true"><span /><span>Label</span><span>Type</span><span>Required</span><span /></div>
              {draftFields.map((field, index) => <div className={`field-row${dragFieldIndex === index ? " is-dragging" : ""}`} key={index} draggable onDragStart={() => setDragFieldIndex(index)} onDragEnd={() => setDragFieldIndex(null)} onDragOver={(event) => event.preventDefault()} onDrop={() => dropField(index)}>
                <span className="drag-handle" aria-hidden="true">⠿</span>
                <input aria-label="Field label" value={field.label} maxLength={120} onChange={(event) => updateField(index, { label: event.target.value, key: field.key })} />
                <select aria-label="Field type" value={field.type} onChange={(event) => updateField(index, { type: event.target.value, options: event.target.value === "dropdown" && field.options.length === 0 ? ["Option 1"] : field.options })}>{FIELD_TYPES.map((type) => <option key={type}>{type}</option>)}</select>
                <label className="field-required"><input type="checkbox" checked={field.required} disabled={field.type === "consent"} onChange={(event) => updateField(index, { required: event.target.checked })} /> Required</label>
                <button type="button" className="field-remove" disabled={Boolean(field.maps_to) || field.type === "consent"} onClick={() => setDraftFields((fields) => fields.filter((_, i) => i !== index))}>Remove</button>
                {field.type === "dropdown" && <input className="field-options" aria-label="Options (comma separated)" placeholder="Option 1, Option 2" value={field.options.join(", ")} onChange={(event) => updateField(index, { options: event.target.value.split(",").map((option) => option.trim()).filter(Boolean) })} />}
              </div>)}
            </div>
            <div className="field-add">
              <span>Mapped and consent fields stay fixed.</span>
              <button type="button" className="button button-secondary" onClick={addField} disabled={draftFields.length >= 25}>Add field ＋</button>
            </div>
          </div>
        </div>

        <div className="content-form-foot">
          <button className="button button-secondary" type="button" onClick={() => setShowForm(false)}>Cancel</button>
          <button className="button button-primary" type="submit" disabled={busy}>{busy ? "Saving…" : "Save form"}</button>
        </div>
      </form>}

      <div className="invoice-list">{forms.length === 0 && <div className="dashboard-empty"><strong>No forms yet</strong><span>Create one, then add it to a page.</span></div>}{forms.map((form) => <article className="invoice-row" key={form.id}><div className="invoice-mark">FRM</div><div className="invoice-main"><h3>{form.name}</h3><p>{form.fields.length} fields · {label(form.action)}</p><small>Version {form.version}</small></div><div className="invoice-actions"><span className={`pipeline-status status-${form.status === "active" ? "paid" : "void"}`}>{form.status}</span>{can("website.edit") && pages.length > 0 && <select aria-label={`Add ${form.name} to page`} defaultValue="" disabled={busy} onChange={(event) => { if (event.target.value) addToPage(form, event.target.value); event.target.value = ""; }}><option value="">Add to page…</option>{pages.map((page) => <option key={page.id} value={page.id}>{page.title}</option>)}</select>}{can("website.edit") && <button className="text-control" disabled={busy} onClick={() => void run(() => patch(`/api/v1/website-content/forms/${form.id}`, { expected_version: form.version, status: form.status === "active" ? "archived" : "active" }), "Form updated.")}>{form.status === "active" ? "Archive" : "Restore"}</button>}</div></article>)}</div>
    </section>}

    {tab === "blog" && <section className="surface-card">
      <div className="surface-card-heading"><div><p className="eyebrow">BLOG</p><h2>Share what you know.</h2></div><div className="content-heading-tools">
        {posts.length > 3 && <input type="search" className="content-search" placeholder="Search posts…" value={search} onChange={(event) => setSearch(event.target.value)} />}
        {can("website.edit") && <button className="button button-primary" onClick={() => { setEditingPost(null); setShowForm((value) => !value); }}>{showForm ? "Close" : "New post"} <span>{showForm ? "×" : "＋"}</span></button>}
      </div></div>

      {(showForm || editingPost) && <form className="content-form" key={editingPost?.id ?? "new"} onSubmit={savePost}>
        <div className="content-form-head">
          <div>
            <p className="eyebrow">{editingPost ? "EDIT POST" : "NEW POST"}</p>
            <h3>{editingPost ? "Polish this article." : "Write a new article."}</h3>
            <p>The title and summary appear on your blog index. The article itself accepts basic HTML.</p>
          </div>
          <span className="content-form-badge">{editingPost ? editingPost.status : "Draft"}</span>
        </div>

        <div className="content-form-body">
          <div className="form-grid">
            <label><span className="field-label">Title <em>up to 200</em></span><input name="title" required maxLength={200} defaultValue={editingPost?.title ?? ""} placeholder="Five questions to ask before your first visit" /></label>
            <label><span className="field-label">Summary <em>up to 400</em></span><input name="excerpt" maxLength={400} defaultValue={editingPost?.excerpt ?? ""} placeholder="One or two lines for the blog index" /></label>
          </div>
          <label className="block-field"><span className="field-label">Article <em>basic HTML allowed · up to 50,000 characters</em></span><textarea name="body" rows={12} maxLength={50000} defaultValue={editingPost?.body ?? ""} placeholder="<p>Start writing…</p>" /></label>

          <details className="content-details">
            <summary><span>SEO settings</span><small>Optional · search title, description, canonical URL</small></summary>
            <div className="form-grid">
              <label><span className="field-label">SEO title <em>up to 70</em></span><input name="seo_title" maxLength={70} placeholder={editingPost?.title ?? "Defaults to post title"} defaultValue={editingPost?.seo_title ?? ""} /></label>
              <label><span className="field-label">Meta description <em>up to 160</em></span><input name="seo_description" maxLength={160} placeholder="Brief summary for search engines" defaultValue={editingPost?.seo_description ?? ""} /></label>
              <label className="field-wide"><span className="field-label">Canonical URL</span><input name="canonical_url" type="url" maxLength={500} placeholder="https://…" defaultValue={editingPost?.canonical_url ?? ""} /></label>
            </div>
          </details>
        </div>

        <div className="content-form-foot">
          <button className="button button-secondary" type="button" onClick={() => { setShowForm(false); setEditingPost(null); }}>Cancel</button>
          <button className="button button-primary" type="submit" disabled={busy}>{busy ? "Saving…" : editingPost ? "Update post" : "Save draft"}</button>
        </div>
      </form>}

      <div className="invoice-list">{filteredPosts.length === 0 && <div className="dashboard-empty"><strong>{search ? "No matching posts" : "No posts yet"}</strong><span>{search ? "Try a different search term." : "Write your first article to share expertise with patients."}</span></div>}{filteredPosts.map((item) => <article className="invoice-row" key={item.id}><div className="invoice-mark">BLG</div><div className="invoice-main"><h3>{item.title}</h3><p>/blog/{item.slug}</p><small>{item.excerpt || "No summary"} · Updated {new Date(item.updated_at).toLocaleDateString()}</small></div><div className="invoice-actions"><span className={`pipeline-status status-${item.status === "published" ? "paid" : "contacted"}`}>{item.status}</span><span className="receipt-links">{can("website.edit") && <button className="text-control" onClick={() => { setShowForm(false); setEditingPost(item); }}>Edit</button>}{can("website.publish") && (item.status === "published" ? <button className="text-control" disabled={busy} onClick={() => void setPostStatus(item, "draft")}>Unpublish</button> : <button className="text-control" disabled={busy} onClick={() => void setPostStatus(item, "published")}>Publish</button>)}</span></div></article>)}</div>
    </section>}

    {tab === "testimonials" && <section className="surface-card">
      <div className="surface-card-heading"><div><p className="eyebrow">TESTIMONIALS</p><h2>Approved reviews only.</h2></div></div>

      {can("website.edit") && <form className="content-form" onSubmit={saveTestimonial}>
        <div className="content-form-head">
          <div>
            <p className="eyebrow">NEW TESTIMONIAL</p>
            <h3>Add a review for approval.</h3>
            <p>Only approved reviews with recorded consent appear on your site.</p>
          </div>
          <span className="content-form-badge">Needs review</span>
        </div>

        <div className="content-form-body">
          <div className="form-grid">
            <label><span className="field-label">Author <em>up to 120 characters</em></span><input name="author" required maxLength={120} placeholder="First name and initial" /></label>
            <label><span className="field-label">Rating</span><select name="rating" defaultValue="5">{[5, 4, 3, 2, 1].map((value) => <option key={value}>{value}</option>)}</select></label>
          </div>
          <label className="block-field"><span className="field-label">Testimonial <em>up to 1,500 characters</em></span><textarea name="body" required rows={5} maxLength={1500} placeholder="What did the patient say about their visit?" /></label>
          <label className="field-narrow"><span className="field-label">Display name as</span><select name="display_name" defaultValue="full"><option value="full">Full name</option><option value="initials">Initials only</option><option value="anonymous">Anonymous</option></select></label>

          <div className="form-checks">
            <label className="inline-check"><input type="checkbox" name="show_rating" defaultChecked /><span>Show the star rating<small>Turn off to publish the words without stars.</small></span></label>
            <label className="inline-check"><input type="checkbox" name="consent" required /><span>Author consented to publication<small>Required before this review can go live.</small></span></label>
          </div>
        </div>

        <div className="content-form-foot"><button className="button button-secondary" type="submit" disabled={busy}>{busy ? "Saving…" : "Add for review"}</button></div>
      </form>}

      <div className="invoice-list">{testimonials.length === 0 && <div className="dashboard-empty"><strong>No testimonials yet</strong></div>}{testimonials.map((item) => <article className="invoice-row" key={item.id}><div className="invoice-mark">{item.show_rating !== false ? `${item.rating}★` : "···"}</div><div className="invoice-main"><h3>{displayName(item)}</h3><p className="content-excerpt">{item.body}</p><small>{item.rating} of 5 · {item.display_name === "initials" ? "Initials only" : item.display_name === "anonymous" ? "Anonymous" : "Full name"}{item.show_rating === false ? " · Rating hidden" : ""}</small></div><div className="invoice-actions"><span className={`pipeline-status status-${item.status === "approved" ? "paid" : item.status === "pending" ? "contacted" : "void"}`}>{item.status}</span>{can("website.publish") && <span className="receipt-links">{item.status !== "approved" && <button className="text-control" disabled={busy} onClick={() => void moderate(item, "approved")}>Approve</button>}{item.status !== "rejected" && <button className="text-control" disabled={busy} onClick={() => void moderate(item, "rejected")}>Reject</button>}</span>}</div></article>)}</div>
    </section>}
  </main>;
}
