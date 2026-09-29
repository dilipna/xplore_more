"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Problems" },
  { href: "/search", label: "Search" },
  { href: "/feed", label: "Feed" },
  { href: "/how-it-works", label: "How it works" },
];

export function NavLinks() {
  const pathname = usePathname();
  return (
    <nav className="-mx-2 flex w-full items-center gap-1 text-sm md:mx-0 md:w-auto">
      {LINKS.map(({ href, label }) => {
        const active = href === "/" ? pathname === "/" || pathname.startsWith("/problems") : pathname.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            className={`whitespace-nowrap rounded-lg px-2 py-1.5 transition-colors md:px-3 ${
              active
                ? "bg-signal-400/10 text-signal-400 shadow-[inset_0_0_0_1px_rgb(57_255_127/0.35),0_0_18px_-4px_rgb(57_255_127/0.5)]"
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
