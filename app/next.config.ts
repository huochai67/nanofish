import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Smaller production image for Docker (node server.js)
  output: "standalone",
  // Hide the bottom-left Next.js dev tools overlay in screenshots
  devIndicators: false,
};

export default nextConfig;
