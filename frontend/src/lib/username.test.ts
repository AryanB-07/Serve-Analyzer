import { describe, expect, it } from "vitest";

import { normaliseUsername, usernameProblem } from "./username";

describe("usernames", () => {
  it("are trimmed, lower-cased and lose a leading @", () => {
    expect(normaliseUsername("  @Ace_Server ")).toBe("ace_server");
  });

  it.each([
    ["ab", "3 to 20"], ["a".repeat(21), "3 to 20"], ["dash-ed", "letters, numbers"], ["émile", "letters, numbers"],
    ["admin", "reserved"], ["support", "reserved"],
  ])("refuses %s", (name, problem) => {
    expect(usernameProblem(name)).toContain(problem);
  });

  it("accepts letters, numbers and underscores", () => {
    expect(usernameProblem("ace_2026")).toBeNull();
    expect(usernameProblem("abc")).toBeNull();
    expect(usernameProblem("a".repeat(20))).toBeNull();
  });
});
