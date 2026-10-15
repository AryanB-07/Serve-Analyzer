import { describe, expect, it } from "vitest";

import { apiQuery, DEFAULT_FILTERS, filtersToParams, isFiltered, parseFilters, type HistoryFilters } from "./historyFilters";

const parse = (qs: string) => parseFilters(new URLSearchParams(qs));

describe("History filters in the URL", () => {
  it("reads every filter and writes the same URL back", () => {
    const qs = "time=custom&from=2026-09-01&to=2026-09-30&score=borderline&stat=trunk_tilt&band=off";
    const f = parse(qs);
    expect(f).toEqual({ time: "custom", from: "2026-09-01", to: "2026-09-30", score: "borderline", stat: "trunk_tilt", band: "off" });
    expect(filtersToParams(f).toString()).toBe(qs);
  });

  it("keeps a plain History URL plain", () => {
    expect(parse("")).toEqual(DEFAULT_FILTERS);
    expect(filtersToParams(DEFAULT_FILTERS).toString()).toBe("");
    expect(isFiltered(DEFAULT_FILTERS)).toBe(false);
    expect(isFiltered({ ...DEFAULT_FILTERS, score: "good" })).toBe(true);
  });

  it("ignores values it doesn't know, and half a stat filter", () => {
    expect(parse("time=forever&score=great&from=yesterday")).toEqual(DEFAULT_FILTERS);
    expect(parse("stat=trunk_tilt")).toEqual(DEFAULT_FILTERS);
    expect(parse("band=good")).toEqual(DEFAULT_FILTERS);
    expect(parse("stat=elbow_wobble&band=good")).toEqual(DEFAULT_FILTERS);
  });

  it("only keeps dates for a custom range", () => {
    const f: HistoryFilters = { ...DEFAULT_FILTERS, time: "7d", from: "2026-09-01", to: "2026-09-30" };
    expect(filtersToParams(f).toString()).toBe("time=7d");
  });
});

describe("the API query", () => {
  const today = new Date("2026-10-14T12:00:00Z");

  it("sends nothing without filters", () => {
    expect(apiQuery(DEFAULT_FILTERS, today)).toEqual({});
  });

  it("turns a preset into a start time", () => {
    expect(apiQuery({ ...DEFAULT_FILTERS, time: "7d" }, today)).toEqual({ uploaded_from: "2026-10-07T12:00:00.000Z" });
    expect(apiQuery({ ...DEFAULT_FILTERS, time: "90d" }, today).uploaded_from).toBe("2026-07-16T12:00:00.000Z");
  });

  it("covers the whole of both custom days, in local time", () => {
    const q = apiQuery({ ...DEFAULT_FILTERS, time: "custom", from: "2026-09-01", to: "2026-09-30" }, today);
    expect(q.uploaded_from).toBe(new Date(2026, 8, 1).toISOString());
    expect(q.uploaded_to).toBe(new Date(2026, 9, 1).toISOString()); // exclusive: the midnight after the 30th
    expect(apiQuery({ ...DEFAULT_FILTERS, time: "custom", from: "2026-09-01" }, today)).not.toHaveProperty("uploaded_to");
  });

  it("maps score bands onto their score ranges", () => {
    expect(apiQuery({ ...DEFAULT_FILTERS, score: "good" })).toEqual({ min_score: "80", max_score: "100" });
    expect(apiQuery({ ...DEFAULT_FILTERS, score: "borderline" })).toEqual({ min_score: "50", max_score: "79" });
    expect(apiQuery({ ...DEFAULT_FILTERS, score: "off" })).toEqual({ min_score: "0", max_score: "49" });
  });

  it("sends a key position with its band", () => {
    expect(apiQuery({ ...DEFAULT_FILTERS, stat: "elbow_angle", band: "borderline" })).toEqual({
      stat: "elbow_angle", stat_band: "borderline",
    });
  });
});
