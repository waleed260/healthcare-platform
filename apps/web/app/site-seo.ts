type SeoPage = { slug: string; noindex?: boolean; canonical_url?: string | null };
type SeoSnapshot = { pages: SeoPage[]; brand?: { seo?: { robots_index?: boolean; disallow_paths?: string[] } } };

const API_ORIGIN = (process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");
const SLUG = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

export function isValidSlug(slug: string) {
  return slug.length <= 120 && SLUG.test(slug);
}

export async function loadSeoSnapshot(slug: string): Promise<SeoSnapshot | null> {
  if (!isValidSlug(slug)) return null;
  try {
    const response = await fetch(`${API_ORIGIN}/api/v1/public/sites/slug/${slug}`, { next: { revalidate: 60 } });
    if (!response.ok) return null;
    const payload = await response.json() as { data?: { snapshot?: SeoSnapshot } };
    return payload.data?.snapshot ?? null;
  } catch {
    return null;
  }
}

const escapeXml = (value: string) => value.replace(/[<>&'"]/g, (char) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;", "'": "&apos;", '"': "&quot;" })[char] as string);

export async function loadPostSlugs(slug: string): Promise<string[]> {
  if (!isValidSlug(slug)) return [];
  try {
    const response = await fetch(`${API_ORIGIN}/api/v1/public/sites/slug/${slug}/posts?limit=50`, { next: { revalidate: 300 } });
    if (!response.ok) return [];
    const payload = await response.json() as { data?: Array<{ slug: string }> };
    return (payload.data ?? []).map((post) => post.slug).filter((value) => isValidSlug(value));
  } catch {
    return [];
  }
}

export function buildSitemap(origin: string, slug: string, snapshot: SeoSnapshot, postSlugs: string[] = []): string {
  const base = `${origin}/${slug}`;
  const urls = [
    ...snapshot.pages.filter((page) => !page.noindex).map((page) => (page.slug === "home" ? base : `${base}/${page.slug}`)),
    ...(postSlugs.length > 0 ? [`${base}/blog`, ...postSlugs.map((post) => `${base}/blog/${post}`)] : []),
  ];
  const body = [...new Set(urls)].map((url) => `  <url><loc>${escapeXml(url)}</loc></url>`).join("\n");
  return `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${body}\n</urlset>\n`;
}

export function buildRobots(origin: string, slug: string, snapshot: SeoSnapshot | null): string {
  const seo = snapshot?.brand?.seo;
  const lines = ["User-agent: *"];
  if (!snapshot || seo?.robots_index === false) lines.push("Disallow: /");
  else {
    lines.push("Allow: /");
    for (const path of seo?.disallow_paths ?? []) if (/^\/[A-Za-z0-9\-._~/*]{0,200}$/.test(path)) lines.push(`Disallow: /${slug}${path}`);
    lines.push("", `Sitemap: ${origin}/${slug}/sitemap.xml`);
  }
  return `${lines.join("\n")}\n`;
}
