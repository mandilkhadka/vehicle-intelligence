/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  images: {
    remotePatterns: [
      {
        protocol: 'http',
        hostname: 'localhost',
        port: '3001',
        pathname: '/uploads/**',
      },
      {
        protocol: 'https',
        hostname: 'images.unsplash.com',
      },
    ],
  },
  async redirects() {
    return [
      {
        source: '/inspect/results',
        has: [{ type: 'query', key: 'id', value: '(?<id>.*)' }],
        destination: '/inspection/:id',
        permanent: true,
      },
    ];
  },
};

module.exports = nextConfig;
