import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "./providers";
import { BasketPanel } from "@/components/basket/BasketPanel";

export const metadata: Metadata = {
  title: "SpliceAnalyzer",
  description: "Exploration d'événements d'épissage différentiel",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr">
      <body className="min-h-screen bg-background font-sans antialiased">
        <Providers>
          <header className="border-b bg-white">
            <div className="max-w-7xl mx-auto px-4 py-3 flex items-center gap-3">
              <a href="/analyses" className="text-lg font-bold text-blue-700 hover:text-blue-900">
                SpliceAnalyzer
              </a>
              <span className="text-sm text-gray-400">Splicing Events Exploration</span>
            </div>
          </header>
          <main className="max-w-7xl mx-auto px-4 py-6">{children}</main>
          <BasketPanel />
        </Providers>
      </body>
    </html>
  );
}
