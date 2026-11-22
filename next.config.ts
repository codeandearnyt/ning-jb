import path from "node:path";

import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // A stray lockfile above this directory makes Next guess the wrong workspace
  // root; pin it so build traces stay inside the project.
  outputFileTracingRoot: path.resolve(process.cwd()),
};

export default nextConfig;
