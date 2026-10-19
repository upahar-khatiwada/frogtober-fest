"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense } from "react";

import type { MessageKey } from "@/lib/i18n/dict";
import { usePrefs } from "@/lib/prefs";
import { cn } from "@/lib/utils";

const LINKS: { href: string; key: MessageKey }[] = [
  { href: "/", key: "nav.dashboard" },
  { href: "/company", key: "nav.company" },
  { href: "/runs", key: "nav.runs" },
];

function Links({ pathname }: { pathname: string | null }) {
  const { t } = usePrefs();
  return (
    <nav aria-label="Main" className="flex items-center gap-1">
      {LINKS.map(({ href, key }) => {
        const active =
          pathname !== null &&
          (href === "/" ? pathname === "/" : pathname.startsWith(href));
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

function ActiveLinks() {
  return <Links pathname={usePathname()} />;
}

/**
 * The pathname of a dynamic route (/tenders/[id]) is request data, so with cacheComponents
 * it must sit inside Suspense. The fallback is the same links with no active highlight.
 */
export function NavLinks() {
  return (
    <Suspense fallback={<Links pathname={null} />}>
      <ActiveLinks />
    </Suspense>
  );
}
