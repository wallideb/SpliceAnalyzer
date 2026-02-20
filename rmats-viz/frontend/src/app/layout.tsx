import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "./providers";
import { BasketPanel } from "@/components/basket/BasketPanel";
import { AppHeader } from "@/components/layout/AppHeader";

export const metadata: Metadata = {
  title: "SpliceAnalyzer",
  description: "Exploration d'événements d'épissage différentiel",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr" suppressHydrationWarning>
      <body className="min-h-screen bg-background font-sans antialiased transition-colors duration-200">
        <Providers>
          <AppHeader />
          <main className="max-w-7xl mx-auto px-4 py-6">{children}</main>
          <BasketPanel />
        </Providers>
      </body>
    </html>
  );
}
