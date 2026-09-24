import { act, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { readingFor } from "../../lib/metricInfo";
import { makeResult } from "../../test/fixtures";
import { renderWithPlayhead } from "../../test/playhead";
import { MetricCard, MetricCards, statusLine } from "./MetricCards";

describe("MetricCard", () => {
  it("shows the value at the key phase, its range and a text status", () => {
    const result = makeResult();
    renderWithPlayhead(<MetricCard reading={readingFor("front_knee_flexion", result)} phases={result.phases} />);
    const card = screen.getByRole("article", { name: "Front knee bend" });
    expect(within(card).getByText("86°")).toBeInTheDocument();
    expect(within(card).getByText("at trophy")).toBeInTheDocument();
    expect(within(card).getByText(/Good range 50°–80° at trophy/)).toBeInTheDocument();
    expect(within(card).getByTestId("metric-status")).toHaveTextContent("Borderline: a little high");
  });

  it("jumps the video to the metric's phase", async () => {
    const result = makeResult();
    const view = renderWithPlayhead(<MetricCard reading={readingFor("wrist_height", result)} phases={result.phases} />);
    await userEvent.click(screen.getByRole("button", { name: /jump to contact/i }));
    expect(view.store.getState().frame).toBe(124);
  });

  it("explains when the phase was not detected", () => {
    const result = makeResult({ phases: { trophy: null, racket_drop: null, contact: 124 } });
    renderWithPlayhead(<MetricCard reading={readingFor("trunk_tilt", result)} phases={result.phases} />);
    expect(screen.getByText("Trophy wasn't detected in this clip.")).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("highlights cards for the phase the video is in", () => {
    const result = makeResult();
    const view = renderWithPlayhead(<MetricCards result={result} />);
    const trophyCard = screen.getByTestId("metric-card-front_knee_flexion");
    const contactCard = screen.getByTestId("metric-card-wrist_height");
    expect(trophyCard.className).not.toMatch(/ring-2/);
    act(() => view.store.reportFrame(113));
    expect(screen.getByTestId("metric-card-front_knee_flexion").className).toMatch(/ring-2/);
    expect(contactCard.className).not.toMatch(/ring-2/);
  });
});

describe("statusLine", () => {
  it("names the status and the direction", () => {
    const base = readingFor("front_knee_flexion", makeResult());
    expect(statusLine({ ...base, status: "good", direction: null })).toBe("Good");
    expect(statusLine({ ...base, status: "off", direction: "low" })).toBe("Needs work: too low");
    expect(statusLine({ ...base, status: "unknown", direction: null })).toBe("Not measured");
  });
});
