import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import { SiteFooter } from "@/components/site-footer";
import { NewsTicker } from "@/components/news-ticker";
import { SiteHeader } from "@/components/site-header";
import "./globals.css";

const inter = Inter({ variable: "--font-inter", subsets: ["latin"] });
const jetbrains = JetBrains_Mono({ variable: "--font-jetbrains", subsets: ["latin"] });

export const metadata: Metadata = {
  title: {
    default: "XploreMore — what engineers are struggling with, ranked by demand",
    template: "%s · XploreMore",
  },
  description:
    "XploreMore mines real pain points from Hacker News, GitHub issues, Lobsters and Stack Exchange, clusters them across people and platforms, and ranks them by demand. Hybrid search and a deduplicated tech feed on the same pipeline.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${inter.variable} ${jetbrains.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col">
        <SiteHeader />
        <NewsTicker />
        <main className="flex-1">{children}</main>
        <SiteFooter />
      </body>
    </html>
  );
}
