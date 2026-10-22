import type { Metadata } from "next";
import { Geist, Geist_Mono, Noto_Sans_Devanagari } from "next/font/google";
import Link from "next/link";

import { NavLinks } from "@/components/app-shell/nav-links";
import { PrefToggles } from "@/components/app-shell/pref-toggles";
import { USE_MOCKS } from "@/lib/config";
import { PreferencesProvider, T } from "@/lib/prefs";

import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

// Devanagari labels, tender titles and BS dates. Geist has no Devanagari glyphs, so the
// font stack in globals.css falls through to Noto for those characters.
const notoDevanagari = Noto_Sans_Devanagari({
  variable: "--font-noto-devanagari",
  subsets: ["devanagari", "latin"],
});

export const metadata: Metadata = {
  title: "Tenderly",
  description: "Tender-to-proposal assistant for Nepali SMEs",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} ${notoDevanagari.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-background text-foreground">
        <PreferencesProvider>
          <a
            href="#main"
            className="sr-only z-20 rounded-md bg-primary px-3 py-2 text-sm text-primary-foreground focus:not-sr-only focus:fixed focus:top-2 focus:left-2"
          >
            <T k="app.skip" />
          </a>
          <header className="sticky top-0 z-10 border-b bg-background/95 backdrop-blur">
            <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
              <Link href="/" className="flex items-baseline gap-2">
                <span className="text-lg font-semibold tracking-tight">Tenderly</span>
                <span className="hidden text-xs text-muted-foreground sm:inline">
                  <T k="app.tagline" />
                </span>
              </Link>
              <NavLinks />
              <div className="ml-auto">
                <PrefToggles />
              </div>
            </div>
            {USE_MOCKS && (
              <div className="border-t bg-amber-50 px-4 py-1.5 text-center text-xs text-amber-900 dark:bg-amber-950 dark:text-amber-100">
                <T k="mock.banner" />
              </div>
            )}
          </header>
          <main id="main" tabIndex={-1} className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 outline-none">{children}</main>
        </PreferencesProvider>
      </body>
    </html>
  );
}
