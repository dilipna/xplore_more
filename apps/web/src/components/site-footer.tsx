const REPO_URL = process.env.XM_REPO_URL ?? "https://github.com/dilipna/xploremore";

export function SiteFooter() {
  return (
    <footer className="border-t hairline">
      <div className="mx-auto flex max-w-6xl flex-col gap-3 px-5 py-8 text-sm text-fg-500 md:flex-row md:items-center md:justify-between">
        <p>
          XploreMore — search, ranking and problem intelligence. No LLM in the serving path; every
          number on this site links to a committed report.
        </p>
        <div className="flex shrink-0 items-center gap-5 font-mono text-xs whitespace-nowrap">
          <a href={REPO_URL} className="hover:text-fg-50" target="_blank" rel="noopener noreferrer">
            source ↗
          </a>
          <a href="https://protopro.vercel.app" className="hover:text-fg-50" target="_blank" rel="noopener noreferrer">
            used by Pro2Pro ↗
          </a>
        </div>
      </div>
    </footer>
  );
}
