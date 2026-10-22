import { describe, expect, it } from "vitest";

import { DICTIONARIES, enumLabel, translate, type MessageKey } from "@/lib/i18n/dict";

const DEVANAGARI = /[ऀ-ॿ]/;
const placeholders = (s: string) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();

describe("dictionary", () => {
  const keys = Object.keys(DICTIONARIES.en) as MessageKey[];

  it("has the same keys in both languages, none empty", () => {
    expect(Object.keys(DICTIONARIES.ne).sort()).toEqual([...keys].sort());
    for (const k of keys) expect(DICTIONARIES.ne[k].trim(), k).not.toBe("");
  });

  it("keeps the same placeholders in both languages", () => {
    for (const k of keys) expect(placeholders(DICTIONARIES.ne[k]), k).toEqual(placeholders(DICTIONARIES.en[k]));
  });

  it("stores Nepali labels as NFC Unicode Devanagari", () => {
    for (const k of keys) {
      const v = DICTIONARIES.ne[k];
      expect(v.normalize("NFC"), k).toBe(v);
    }
    const devanagari = keys.filter((k) => DEVANAGARI.test(DICTIONARIES.ne[k]));
    // Brand name and a few code-like labels stay Latin; everything else is translated.
    expect(devanagari.length).toBeGreaterThan(keys.length * 0.95);
  });
});

describe("translate", () => {
  it("fills placeholders, with Devanagari digits for numbers in Nepali", () => {
    expect(translate("en", "dashboard.count", { n: 12 })).toBe("12 tenders");
    expect(translate("ne", "dashboard.count", { n: 12 })).toBe("१२ बोलपत्र");
    expect(translate("ne", "dashboard.loadFailed", { error: "HTTP 500" })).toBe("बोलपत्र लोड हुन सकेन: HTTP 500");
  });

  it("leaves unknown placeholders visible", () => {
    expect(translate("en", "pp.s.chunk")).toContain("{id}");
  });

  it("labels API enum values and passes unknown ones through", () => {
    expect(enumLabel("ne", "province", "gandaki")).toBe("गण्डकी");
    expect(enumLabel("en", "method", "quotation")).toBe("Sealed quotation");
    expect(enumLabel("ne", "status", "blocked")).toBe("रोकियो");
    expect(enumLabel("en", "status", "something_new")).toBe("something_new");
  });
});
