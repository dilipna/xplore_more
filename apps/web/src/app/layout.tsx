import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import { CommandPalette } from "@/components/command-palette";
import { KeyboardShortcuts } from "@/components/keyboard-shortcuts";
import { SiteFooter } from "@/components/site-footer";
import { NewsTicker } from "@/components/news-ticker";
import { SiteHeader } from "@/components/site-header";
import { recordedMode } from "@/lib/web-mode";
import { CaptureBanner } from "@/components/capture-banner";
import "./globals.css";

const inter = Inter({ variable: "--font-inter", subsets: ["latin"] });
const jetbrains = JetBrains_Mono({ variable: "--font-jetbrains", subsets: ["latin"] });

export const metadata: Metadata = {
  title: {
    default: "XploreMore: tech news and the problems engineers keep reporting",
    template: "%s · XploreMore",
  },
  description:
    "Source-linked technology stories and engineer-reported problems, with explainable ranking and a dated, inspectable public capture.",
  applicationName: "XploreMore",
  alternates: {
    types: {
      "application/rss+xml": [
        { url: "/rss.xml", title: "XploreMore: top stories" },
        { url: "/problems.xml", title: "XploreMore: most reported problems" },
      ],
      "application/feed+json": [{ url: "/feed.json", title: "XploreMore: top stories (JSON Feed)" }],
    },
  },
  openGraph: { siteName: "XploreMore", type: "website" },
  twitter: { card: "summary" },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${inter.variable} ${jetbrains.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col">
        <SiteHeader />
        {recordedMode() && <CaptureBanner />}
        <NewsTicker />
        <main className="flex-1">{children}</main>
        <SiteFooter />
        <KeyboardShortcuts />
        <CommandPalette recorded={recordedMode()} />
      </body>
    </html>
  );
}
