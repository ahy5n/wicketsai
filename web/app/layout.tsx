import type { Metadata, Viewport } from "next";
import { Inter, Source_Serif_4 } from "next/font/google";
import "./globals.css";
import { SessionProvider } from "@/components/session";
import { Header } from "@/components/header";

const serif = Source_Serif_4({ subsets: ["latin"], variable: "--font-serif-face", display: "swap" });
const sans = Inter({ subsets: ["latin"], variable: "--font-sans-face", display: "swap" });

export const metadata: Metadata = {
  title: "Wickets.ai",
  description: "Every T20I ball. Any question. With the receipts.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${serif.variable} ${sans.variable}`}>
      <body className="min-h-dvh flex flex-col">
        <SessionProvider>
          <Header />
          <main className="flex-1 w-full max-w-5xl mx-auto px-4 sm:px-6 py-6 sm:py-10">{children}</main>
          <footer className="border-t border-rule text-xs text-muted">
            <div className="max-w-5xl mx-auto px-4 sm:px-6 py-5 flex flex-col sm:flex-row gap-2 justify-between">
              <span>Data from Cricsheet (cricsheet.org), ODC-BY. Player profiles from Wikipedia, CC BY-SA.</span>
              <span>Men&apos;s and women&apos;s T20Is, ball by ball.</span>
            </div>
          </footer>
        </SessionProvider>
      </body>
    </html>
  );
}
