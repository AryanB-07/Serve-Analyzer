import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { makeResult } from "../../test/fixtures";
import { renderWithPlayhead } from "../../test/playhead";
import { FeedbackPanel } from "./FeedbackPanel";

describe("FeedbackPanel", () => {
  it("jumps to the phase each point is about", async () => {
    const view = renderWithPlayhead(<FeedbackPanel result={makeResult()} />);
    await userEvent.click(screen.getByRole("button", { name: /front knee/i }));
    expect(view.store.getState().frame).toBe(113);
    await userEvent.click(screen.getByRole("button", { name: /hit the ball higher/i }));
    expect(view.store.getState().frame).toBe(124);
  });

  it("does not link points whose phase is missing or absent", () => {
    const result = makeResult({
      phases: { trophy: null, racket_drop: null, contact: 124 },
      feedback: [
        { text: "Knee point", phase: "trophy", metric: "front_knee_flexion", status: "off" },
        { text: "Nice serve!", phase: null, metric: null, status: "good" },
      ],
    });
    renderWithPlayhead(<FeedbackPanel result={result} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });
});
