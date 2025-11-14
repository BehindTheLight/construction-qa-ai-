import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Demo — Construction Ask & Cite",
  description: "AI assistant for construction documents with precise citations",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}

