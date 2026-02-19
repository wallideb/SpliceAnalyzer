import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "rMATS Visualizer — PCBP1",
  description: "Differential splicing event viewer for PCBP1 variant patients",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr">
      <body className="min-h-screen bg-background font-sans antialiased">
        <Providers>
          <header className="border-b bg-white">
            <div className="max-w-7xl mx-auto px-4 py-3 flex items-center gap-3">
              <a href="/analyses" className="text-lg font-bold text-blue-700 hover:text-blue-900">
                rMATS Visualizer
              </a>
              <span className="text-sm text-gray-400">PCBP1 Splicing Events</span>
            </div>
          </header>
          <main className="max-w-7xl mx-auto px-4 py-6">{children}</main>
        </Providers>
      </body>
    </html>
  );
}
