import type { NextConfig } from "next";

const API = process.env.WICKETS_API_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  // The Python API (wickets/api.py) serves /api/*; proxying keeps cookies same-origin.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API}/api/:path*` }];
  },
  experimental: {
    // Questions can take a minute or more (several model turns); the default proxy timeout is 30s.
    proxyTimeout: 180_000,
  },
};

export default nextConfig;
