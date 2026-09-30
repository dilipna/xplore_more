import Link from "next/link";

const REPO_URL = process.env.XM_REPO_URL ?? "https://github.com/dilipna/xplore_more";

export function SiteFooter() {
  return (
    <footer className="border-t hairline print:hidden">
      <div className="mx-auto flex max-w-6xl flex-col gap-3 px-5 py-6 text-sm text-fg-500 md:flex-row md:items-center md:justify-between">
        <p>
          <span className="text-fg-200">XploreMore</span> · built by Dilip Nallamasa
        </p>
        <div className="flex items-center gap-5">
          <Link href="/how-it-works" className="hover:text-signal-300">
            About
          </Link>
          <a href={REPO_URL} className="hover:text-signal-300" target="_blank" rel="noopener noreferrer">
            GitHub
          </a>
          <a href="https://protopro.vercel.app" className="hover:text-signal-300" target="_blank" rel="noopener noreferrer">
            Pro2Pro
          </a>
        </div>
      </div>
    </footer>
  );
}
