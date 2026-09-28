import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Standalone output: `next build` emits server.js plus only the traced dependencies, so the
  // Cloud Run image ships without the full node_modules tree.
  output: "standalone",
  poweredByHeader: false,
};

export default nextConfig;
