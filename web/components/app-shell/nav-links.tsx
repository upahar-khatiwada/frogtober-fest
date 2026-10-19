"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import type { MessageKey } from "@/lib/i18n/dict";
import { usePrefs } from "@/lib/prefs";
import { cn } from "@/lib/utils";

const LINKS: { href: string; key: MessageKey }[] = [
  { href: "/", key: "nav.dashboard" },
  { href: "/company", key: "nav.company" },
  { href: "/runs", key: "nav.runs" },
];

export function NavLinks() {
  const pathname = usePathname();
  const { t } = usePrefs();
  return (
    <nav aria-label="Main" className="flex items-center gap-1">
      {LINKS.map(({ href, key }) => {
        const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "rounded-md px-3 py-1.5 text-sm font-medium transition-colors hover:bg-muted",
              active ? "bg-muted text-foreground" : "text-muted-foreground",
            )}
          >
            {t(key)}
          </Link>
        );
      })}
    </nav>
  );
}
