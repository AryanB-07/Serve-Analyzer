import { describe, expect, it } from "vitest";

import { nextParam, safeNext } from "./safeNext";

describe("safeNext", () => {
  it("keeps paths inside the app, with their query", () => {
    expect(safeNext("/history")).toBe("/history");
    expect(safeNext("/analyses/abc?tab=charts")).toBe("/analyses/abc?tab=charts");
  });

  it.each([null, undefined, "", "history", "//evil.example", "/\\evil.example", "https://evil.example", "javascript:alert(1)"])(
    "falls back to the home page for %s",
    (raw) => expect(safeNext(raw)).toBe("/"),
  );

  it("never loops back to the sign-in pages", () => {
    expect(safeNext("/login")).toBe("/");
    expect(safeNext("/signup?next=/history")).toBe("/");
  });
});

describe("nextParam", () => {
  it("omits the home page and encodes everything else", () => {
    expect(nextParam("/")).toBe("");
    expect(nextParam("/analyses/a b?x=1")).toBe("?next=%2Fanalyses%2Fa%20b%3Fx%3D1");
  });
});
