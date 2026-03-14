/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: {
    // Large file uploads (200 MB+), analysis deletes (100 k+ row batches), and
    // PDF/Excel exports all need more than the default 60-second proxy window.
    proxyTimeout: 600_000,   // 10 min
  },
  async rewrites() {
    // All /api/* requests are forwarded to the FastAPI backend.
    // Using beforeFiles so this runs before Next.js checks its own route
    // handlers, which guarantees DELETE/PATCH etc. are never blocked by a
    // stale in-memory route entry from a previously-deleted route.ts file.
    return {
      beforeFiles: [
        {
          source: "/api/:path*",
          destination: `${process.env.API_URL || "http://localhost:8000"}/api/:path*`,
        },
      ],
    };
  },
};

export default nextConfig;
