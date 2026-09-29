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
              active ? "bg-field-800 text-fg-50" : "text-fg-400 hover:text-fg-50"
            }`}
          >
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
