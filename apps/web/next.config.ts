import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  outputFileTracingRoot: path.join(process.cwd(), "../.."),
  experimental: {
    useTypeScriptCli: false,
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
    return [{ source: "/api/:path*", destination: `${apiOrigin.replace(/\/$/, "")}/api/:path*` }];
  },
};
export default nextConfig;
