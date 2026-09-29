import { Suspense } from "react";
import { LeftNav } from "./left-nav";

/** Three-column social layout: sections on the left (desktop), the feed, a rail on the right. */
export function Shell({ children, rail }: { children: React.ReactNode; rail?: React.ReactNode }) {
  return (
    <div className="mx-auto grid max-w-7xl gap-6 px-4 py-6 sm:px-5 lg:grid-cols-[210px_minmax(0,1fr)] xl:grid-cols-[210px_minmax(0,1fr)_320px]">
      <aside className="hidden lg:block">
        {/* useSearchParams needs a Suspense boundary so the rest of the page can stream. */}
        <Suspense>
          <LeftNav />
        </Suspense>
      </aside>
      <div className="min-w-0">{children}</div>
      {rail && <aside className="hidden min-w-0 xl:block">{rail}</aside>}
    </div>
  );
}
