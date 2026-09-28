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
    <nav className="flex items-center gap-1 text-sm">
      {LINKS.map(({ href, label }) => {
        const active = href === "/" ? pathname === "/" || pathname.startsWith("/problems") : pathname.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            className={`rounded-lg px-3 py-1.5 transition-colors ${
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
