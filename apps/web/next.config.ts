import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  outputFileTracingRoot: path.join(process.cwd(), "../.."),
  async rewrites() {
    const apiOrigin = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    return [{ source: "/api/:path*", destination: `${apiOrigin.replace(/\/$/, "")}/api/:path*` }];
  },
};
export default nextConfig;
