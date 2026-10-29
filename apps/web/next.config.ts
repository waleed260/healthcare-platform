import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  outputFileTracingRoot: path.join(process.cwd(), "../.."),
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  compress: true,
  poweredByHeader: false,
  reactStrictMode: true,
  experimental: {
    useTypeScriptCli: false,
  },
  async headers() {
    return [
      {
        source: "/_next/static/:path*",
        headers: [{ key: "Cache-Control", value: "public, max-age=31536000, immutable" }],
      },
      {
        source: "/fonts/:path*",
        headers: [{ key: "Cache-Control", value: "public, max-age=31536000, immutable" }],
      },
      {
        source: "/:clinicSlug((?!api|_next|login|onboarding|setup|dashboard|schedule|patients|leads|queue|operations|doctors|encounters|branches|services|clinical|billing|finance|packages|reports|inventory|website|content|domains|media|analytics|manage|notifications|security|privacy|admin|book|reset-password)[a-z0-9-]+)",
        headers: [{ key: "Cache-Control", value: "public, max-age=60, s-maxage=300, stale-while-revalidate=600" }],
      },
    ];
  },
  async rewrites() {
    const apiOrigin = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    let parsedOrigin: URL;
    try {
      parsedOrigin = new URL(apiOrigin);
    } catch (error) {
      throw new Error(`API_URL must be an absolute HTTP(S) URL: ${String(error)}`);
    }
    if (!(["http:", "https:"] as string[]).includes(parsedOrigin.protocol)) {
      throw new Error("API_URL must use http or https");
    }
    return [
      { source: "/api/:path*", destination: `${apiOrigin.replace(/\/$/, "")}/api/:path*` },
      { source: "/health/:path*", destination: `${apiOrigin.replace(/\/$/, "")}/health/:path*` },
      { source: "/:clinicSlug/sitemap.xml", destination: "/:clinicSlug/sitemap-feed" },
    ];
  },
};
export default nextConfig;
