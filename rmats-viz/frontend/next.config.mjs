/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: {
    proxyTimeout: 600_000,   // 10 min – large file uploads (200 MB+) need time to parse & store
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.API_URL || "http://localhost:8000"}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
