import type { Metadata } from "next";
import PublicSite from "./site-view";

type Snapshot = { brand?: { seo?: { site_name?: string | null; robots_index?: boolean } }; pages?: { slug: string; title: string; seo_title?: string | null; seo_description?: string | null; noindex?: boolean }[] };

export async function generateMetadata({ params }: { params: Promise<{ clinicSlug: string }> }): Promise<Metadata> {
  const { clinicSlug } = await params;
  const origin = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  try {
    const response = await fetch(`${origin}/api/v1/public/sites/slug/${encodeURIComponent(clinicSlug)}`, { next: { revalidate: 60 }, headers: { "ngrok-skip-browser-warning": "1" } });
    if (!response.ok) return {};
    const payload = await response.json() as { data?: { snapshot?: Snapshot } };
    const snapshot = payload.data?.snapshot;
    const page = snapshot?.pages?.find((item) => item.slug === "home") ?? snapshot?.pages?.[0];
    if (!page) return {};
    const title = page.seo_title || page.title;
    const noindex = page.noindex || snapshot?.brand?.seo?.robots_index === false;
    return {
      title,
      description: page.seo_description ?? undefined,
      openGraph: { title, description: page.seo_description ?? undefined, type: "website", siteName: snapshot?.brand?.seo?.site_name ?? undefined },
      robots: noindex ? { index: false, follow: false } : { index: true, follow: true },
    };
  } catch {
    return {};
  }
}

export default function ClinicHomePage() {
  return <PublicSite />;
}
