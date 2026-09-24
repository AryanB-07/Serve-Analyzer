import { fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { renderWithPlayhead } from "../../test/playhead";
import { PhaseTimeline } from "./PhaseTimeline";

const phases = { trophy: 113, racket_drop: null, contact: 124 };

describe("PhaseTimeline", () => {
  it("seeks to the contact frame when its marker is clicked", async () => {
    const view = renderWithPlayhead(<PhaseTimeline phases={phases} />);
    await userEvent.click(screen.getByRole("button", { name: /jump to contact/i }));
    expect(view.store.getState().frame).toBe(124);
    expect(view.commands.at(-1)).toEqual({ type: "seek", frame: 124 });
  });

  it("seeks to a segment's start from its chip, and back to the stance", async () => {
    const view = renderWithPlayhead(<PhaseTimeline phases={phases} />);
    await userEvent.click(screen.getByRole("button", { name: /^trophy/i }));
    expect(view.store.getState().frame).toBe(113);
    await userEvent.click(screen.getByRole("button", { name: /^stance/i }));
    expect(view.store.getState().frame).toBe(0);
  });

  it("shows undetected phases as not clickable", () => {
    renderWithPlayhead(<PhaseTimeline phases={phases} />);
    expect(screen.getByText(/not detected/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /racket drop/i })).not.toBeInTheDocument();
  });

  it("seeks to the frame under the pointer on the track", () => {
    const view = renderWithPlayhead(<PhaseTimeline phases={phases} />);
    const track = screen.getByRole("slider", { name: "Timeline" });
    track.getBoundingClientRect = () => ({ left: 100, width: 500, top: 0, height: 36, right: 600, bottom: 36, x: 100, y: 0, toJSON() {} });
    fireEvent.pointerDown(track, { clientX: 350, pointerId: 1 });
    expect(view.store.getState().frame).toBe(62);
  });

  it("keeps the slider's accessible value in step with the playhead", () => {
    const view = renderWithPlayhead(<PhaseTimeline phases={phases} />);
    const track = screen.getByRole("slider", { name: "Timeline" });
    view.store.reportFrame(113);
    expect(track).toHaveAttribute("aria-valuenow", "114");
    expect(track.getAttribute("aria-valuetext")).toMatch(/Frame 114 of 125.*Trophy/);
  });
});
