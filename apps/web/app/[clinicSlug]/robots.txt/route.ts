import { buildRobots, loadSeoSnapshot } from "../../site-seo";

export async function GET(request: Request, { params }: { params: Promise<{ clinicSlug: string }> }) {
  const { clinicSlug } = await params;
  const snapshot = await loadSeoSnapshot(clinicSlug);
  return new Response(buildRobots(new URL(request.url).origin, clinicSlug, snapshot), { headers: { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "public, max-age=300" } });
}
