/** @type {import('next').NextConfig} */
const path = require("path");
const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:3001";

const nextConfig = {
  reactStrictMode: true,
  turbopack: {
    root: path.resolve(__dirname, ".."),
  },
  images: {
    // Next 16 blocks remote optimization to private IPs (localhost), so we
    // proxy /uploads through Next instead and use localPatterns.
    localPatterns: [
      { pathname: "/uploads/**", search: "" },
      { pathname: "/images/**", search: "" },
      { pathname: "/placeholder.svg", search: "" },
    ],
    remotePatterns: [
      {
        protocol: "https",
        hostname: "images.unsplash.com",
        pathname: "/**",
        search: "",
      },
    ],
  },
  async rewrites() {
    return [
      { source: "/uploads/:path*", destination: `${BACKEND_URL}/uploads/:path*` },
    ];
  },
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          {
            // Allow camera on same-origin so the /capture guided walkaround
            // can prompt for it; everything else stays denied.
            key: "Permissions-Policy",
            value: "camera=(self), microphone=(), geolocation=(), payment=()",
          },
        ],
      },
    ];
  },
};

module.exports = nextConfig;
