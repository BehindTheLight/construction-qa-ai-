/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  webpack: (config, { isServer }) => {
    // Fix for pdfjs-dist
    if (!isServer) {
      config.resolve.alias.canvas = false;
    }
    
    // Handle PDF.js worker
    config.resolve.alias['pdfjs-dist'] = 'pdfjs-dist/build/pdf';
    
    return config;
  },
}

module.exports = nextConfig

