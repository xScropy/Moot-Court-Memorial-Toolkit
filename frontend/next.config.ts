import type { NextConfig } from "next";

// DESKTOP_BUILD=1 produces a static site that the packaged app serves itself.
const desktop = process.env.DESKTOP_BUILD === "1";

const nextConfig: NextConfig = {
  ...(desktop ? { output: "export" as const, trailingSlash: true } : {}),
  /* config options here */
  cacheComponents: !desktop,
  partialPrefetching: !desktop,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
