import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "IncidentCast",
  description: "AI incident room: four Splunk-powered specialists, one evidence-cited deck.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen text-ink-100 antialiased">{children}</body>
    </html>
  );
}
