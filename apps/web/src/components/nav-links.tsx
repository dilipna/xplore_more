"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "News" },
  { href: "/problems", label: "Problems" },
  { href: "/search", label: "Search" },
  { href: "/topics", label: "My topics" },
  { href: "/how-it-works", label: "About" },
];

export function NavLinks() {
  const pathname = usePathname();
  return (
    <nav className="-mx-2 flex w-full items-center gap-1 text-sm md:mx-0 md:w-auto">
      {LINKS.map(({ href, label }) => {
        const active =
          href === "/" ? pathname === "/" || pathname.startsWith("/feed") || pathname.startsWith("/stories") : pathname.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            className={`whitespace-nowrap rounded-lg px-2 py-1.5 transition-colors md:px-3 ${
              active
                ? "bg-signal-400/10 text-signal-400"
                : "text-fg-400 hover:text-signal-300"
            }`}
          >
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
