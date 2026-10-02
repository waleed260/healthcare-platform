import { buildSitemap, loadPostSlugs, loadSeoSnapshot } from "../../site-seo";

export async function GET(request: Request, { params }: { params: Promise<{ clinicSlug: string }> }) {
  const { clinicSlug } = await params;
  const snapshot = await loadSeoSnapshot(clinicSlug);
  if (!snapshot) return new Response("Not found", { status: 404 });
  return new Response(buildSitemap(new URL(request.url).origin, clinicSlug, snapshot, await loadPostSlugs(clinicSlug)), { headers: { "Content-Type": "application/xml; charset=utf-8", "Cache-Control": "public, max-age=300" } });
}
