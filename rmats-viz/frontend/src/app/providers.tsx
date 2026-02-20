"use client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { BasketProvider } from "@/contexts/BasketContext";
import { ThemeProvider } from "@/contexts/ThemeContext";

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(() => new QueryClient({ defaultOptions: { queries: { staleTime: 30_000 } } }));
  return (
    <QueryClientProvider client={client}>
      <ThemeProvider>
        <BasketProvider>{children}</BasketProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
