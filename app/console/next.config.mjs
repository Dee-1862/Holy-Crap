/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Checks can build into another folder so a running dev server keeps its own .next.
  distDir: process.env.NEXT_DIST_DIR || ".next",
};

export default nextConfig;
