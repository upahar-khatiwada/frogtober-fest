import { describe, expect, it } from "vitest";

import { countdown, countdownFromView, countdownText, daysLeftNpt, nptDate, nptTime } from "@/lib/deadline";

const NOW = new Date("2026-10-19T12:00:00+05:45");

describe("NPT calendar days", () => {
  it("rolls over to the next NPT day at 18:15 UTC", () => {
    expect(nptDate(new Date("2026-10-17T18:14:59Z"))).toBe("2026-10-17");
    expect(nptDate(new Date("2026-10-17T18:15:00Z"))).toBe("2026-10-18");
  });

  it("matches the API's days_left (api/tests/test_tenders_list_api.py)", () => {
    expect(daysLeftNpt(new Date("2026-11-21T12:00:00+05:45"), NOW)).toBe(33);
  });

  it("counts calendar days, not 24-hour periods", () => {
    // 23:50 NPT tonight to 00:10 NPT tomorrow is 20 minutes but one calendar day.
    expect(daysLeftNpt(new Date("2026-10-20T00:10:00+05:45"), new Date("2026-10-19T23:50:00+05:45"))).toBe(1);
  });
});

describe("countdown", () => {
  it("is ok far out", () => {
    const c = countdown("2026-11-21T12:00:00+05:45", NOW);
    expect(c).toMatchObject({ passed: false, daysLeft: 33, urgency: "ok" });
    expect(countdownText(c, "en")).toBe("33 days left");
    expect(countdownText(c, "ne")).toBe("३३ दिन बाँकी");
  });

  it("is soon within 7 days and urgent within 3", () => {
    expect(countdown("2026-10-25T12:00:00+05:45", NOW).urgency).toBe("soon");
    expect(countdown("2026-10-22T12:00:00+05:45", NOW).urgency).toBe("urgent");
  });

  it("shows hours and minutes in the last 24 hours", () => {
    const today = countdown("2026-10-19T17:30:00+05:45", NOW);
    expect(today).toMatchObject({ daysLeft: 0, hours: 5, minutes: 30, urgency: "today" });
    expect(countdownText(today, "en")).toBe("Due today, 5h 30m left");
    const tomorrow = countdown("2026-10-20T10:00:00+05:45", NOW);
    expect(countdownText(tomorrow, "en")).toBe("22h 0m left");
    expect(countdownText(tomorrow, "ne")).toBe("२२ घण्टा ० मिनेट बाँकी");
  });

  it("is passed at the deadline instant", () => {
    expect(countdown("2026-10-19T12:00:00+05:45", NOW)).toMatchObject({ passed: true, urgency: "passed", hours: 0 });
    const old = countdown("2026-10-14T12:00:00+05:45", NOW);
    expect(countdownText(old, "en")).toBe("Passed 5 days ago");
    expect(countdownText(old, "ne")).toBe("५ दिन अघि म्याद सकियो");
    expect(countdownText(countdown("2026-10-19T09:00:00+05:45", NOW), "en")).toBe("Passed today");
  });

  it("falls back to the API's view before the live clock starts", () => {
    expect(countdownText(countdownFromView({ days_left: 33, passed: false }), "en")).toBe("33 days left");
    expect(countdownText(countdownFromView({ days_left: 0, passed: false }), "en")).toBe("Due today");
    expect(countdownText(countdownFromView({ days_left: 1, passed: false }), "en")).toBe("1 day left");
    expect(countdownText(countdownFromView({ days_left: -2, passed: true }), "en")).toBe("Passed 2 days ago");
  });

  it("rejects an invalid deadline", () => {
    expect(() => countdown("not a date", NOW)).toThrow();
  });

  it("prints the NPT time of day", () => {
    expect(nptTime("2026-11-21T06:15:00Z")).toBe("12:00");
  });
});
