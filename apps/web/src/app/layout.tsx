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
    default: "XploreMore: tech news and the problems engineers keep reporting",
    template: "%s · XploreMore",
  },
  description:
    "Top tech stories from 43 sources, one story per event, plus the problems engineers keep reporting on Hacker News, GitHub, Lobsters and Stack Exchange.",
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
