"use client";

import { useParams } from "next/navigation";
import PublicSite from "../site-view";

export default function ClinicContentPage() {
  const { pageSlug } = useParams<{ pageSlug: string }>();
  return <PublicSite pageSlug={pageSlug} />;
}
