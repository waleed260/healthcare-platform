"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { SiteFooter, SiteHeader } from "./site-chrome";
import { themeStyle } from "../site-theme";
import type { SiteBrand } from "../site-theme";

type PostSummary = { slug: string; title: string; excerpt: string; published_at: string };
type Post = PostSummary & { body: string; seo_title: string | null; seo_description: string | null };

function useSite(clinicSlug: string) {
  const [brand, setBrand] = useState<SiteBrand>({});
  useEffect(() => {
    void fetch(`/api/v1/public/sites/slug/${encodeURIComponent(clinicSlug)}`, { cache: "no-store" }).then((response) => response.ok ? response.json() : null).then((payload) => setBrand((payload?.data?.snapshot?.brand as SiteBrand | undefined) ?? {})).catch(() => undefined);
  }, [clinicSlug]);
  return brand;
}

function Frame({ clinicSlug, brand, children }: { clinicSlug: string; brand: SiteBrand; children: ReactNode }) {
  return <main className="public-site has-theme" style={themeStyle(brand)}><SiteHeader brand={brand} clinicSlug={clinicSlug} /><div className="public-shell">{children}</div><SiteFooter brand={brand} title="Blog" clinicSlug={clinicSlug} /></main>;
}

export function BlogList() {
  const { clinicSlug } = useParams<{ clinicSlug: string }>();
  const brand = useSite(clinicSlug);
  const [posts, setPosts] = useState<PostSummary[] | null>(null);
  useEffect(() => {
    void fetch(`/api/v1/public/sites/slug/${encodeURIComponent(clinicSlug)}/posts`, { cache: "no-store" }).then((response) => response.ok ? response.json() : { data: [] }).then((payload) => setPosts(payload.data as PostSummary[])).catch(() => setPosts([]));
  }, [clinicSlug]);
  useEffect(() => { const previous = document.title; document.title = "Blog"; return () => { document.title = previous; }; }, []);
  return <Frame clinicSlug={clinicSlug} brand={brand}><div className="blog-list"><h1>Blog</h1>{posts === null ? <p role="status">Loading…</p> : posts.length === 0 ? <p>No articles yet.</p> : posts.map((post) => <article key={post.slug}><h2><Link href={`/${clinicSlug}/blog/${post.slug}`}>{post.title}</Link></h2><p>{post.excerpt}</p><small>{new Date(post.published_at).toLocaleDateString()}</small></article>)}</div></Frame>;
}

export function BlogPost() {
  const { clinicSlug, postSlug } = useParams<{ clinicSlug: string; postSlug: string }>();
  const brand = useSite(clinicSlug);
  const [post, setPost] = useState<Post | null | undefined>(undefined);
  useEffect(() => {
    void fetch(`/api/v1/public/sites/slug/${encodeURIComponent(clinicSlug)}/posts/${encodeURIComponent(postSlug)}`, { cache: "no-store" }).then((response) => response.ok ? response.json() : null).then((payload) => setPost((payload?.data as Post | undefined) ?? null)).catch(() => setPost(null));
  }, [clinicSlug, postSlug]);
  useEffect(() => {
    if (!post) return;
    const previous = document.title;
    document.title = post.seo_title || post.title;
    const description = document.createElement("meta");
    description.name = "description";
    description.content = post.seo_description || post.excerpt;
    document.head.appendChild(description);
    return () => { document.title = previous; description.remove(); };
  }, [post]);
  if (post === null) return <Frame clinicSlug={clinicSlug} brand={brand}><div className="blog-list"><h1>Article not found</h1><Link href={`/${clinicSlug}/blog`}>Back to the blog</Link></div></Frame>;
  if (post === undefined) return <Frame clinicSlug={clinicSlug} brand={brand}><p role="status">Loading…</p></Frame>;
  return <Frame clinicSlug={clinicSlug} brand={brand}><article className="dynamic-page"><h1>{post.title}</h1><small>{new Date(post.published_at).toLocaleDateString()}</small><div className="blog-body" dangerouslySetInnerHTML={{ __html: post.body }} /><Link href={`/${clinicSlug}/blog`}>← All articles</Link></article></Frame>;
}
