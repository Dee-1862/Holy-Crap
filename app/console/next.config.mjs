/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Checks can build into another folder so a running dev server keeps its own .next.
  distDir: process.env.NEXT_DIST_DIR || ".next",
  // media (clips, up to several GB) and .data are read at run time from disk, never bundled into the server.
  outputFileTracingExcludes: { "*": ["media/**", ".data/**"] },
};

export default nextConfig;
