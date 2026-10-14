/** "Where was your camera?" on the upload form. */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import type { Hand } from "../../api/types";
import type { CameraView } from "../../lib/quality";
import { CameraPicker } from "./CameraPicker";
import { runUpload } from "./runUpload";

function Harness({ hand, onChange }: { hand: Hand | null; onChange?: (v: CameraView | null) => void }) {
  const [value, setValue] = useState<CameraView | null>(null);
  return (
    <CameraPicker
      value={value}
      hand={hand}
      onChange={(v) => {
        setValue(v);
        onChange?.(v);
      }}
    />
  );
}

describe("the camera picker", () => {
  it("offers the eight positions and not sure, starting at not sure", () => {
    render(<Harness hand="right" />);
    const group = screen.getByRole("group", { name: /Where was your camera\? \(optional\)/ });
    const radios = within(group).getAllByRole("radio");
    expect(radios).toHaveLength(9);
    expect(within(group).getByRole("radio", { name: "Not sure, or skip" })).toBeChecked();
    for (const name of [
      "Side-on, from your hitting-arm side", "Side-on, from your tossing-arm side", "From behind the baseline",
      "From across the net", "From a back corner, on your hitting-arm side", "From a front corner, on your tossing-arm side",
    ]) {
      expect(within(group).getByRole("radio", { name })).toBeInTheDocument();
    }
  });

  it("records the choice, and lets it go back to not sure", async () => {
    const onChange = vi.fn();
    render(<Harness hand="right" onChange={onChange} />);
    await userEvent.click(screen.getByRole("radio", { name: "Side-on, from your hitting-arm side" }));
    expect(onChange).toHaveBeenLastCalledWith("side_hitting");
    expect(screen.getByRole("radio", { name: "Side-on, from your hitting-arm side" })).toBeChecked();
    await userEvent.click(screen.getByRole("radio", { name: "Not sure, or skip" }));
    expect(onChange).toHaveBeenLastCalledWith(null);
  });

  it("puts the hitting-arm side on the right for right-handers and the left for left-handers", () => {
    const order = () => screen.getAllByRole("radio").map((r) => r.getAttribute("value"));
    const { unmount } = render(<Harness hand="right" />);
    expect(order().slice(0, 8)).toEqual([
      "front_diagonal_toss", "front", "front_diagonal_hitting", "side_toss", "side_hitting",
      "behind_diagonal_toss", "behind", "behind_diagonal_hitting",
    ]);
    unmount();
    render(<Harness hand="left" />);
    expect(order().slice(0, 8)).toEqual([
      "front_diagonal_hitting", "front", "front_diagonal_toss", "side_hitting", "side_toss",
      "behind_diagonal_hitting", "behind", "behind_diagonal_toss",
    ]);
  });

  it("asks for the hand first when it isn't chosen yet", () => {
    render(<Harness hand={null} />);
    expect(screen.getByText(/Choose your hand first/)).toBeInTheDocument();
  });

  it("is sent with the upload", async () => {
    const client = {
      createAnalysis: vi.fn(async () => ({ analysis: { id: "a1" }, upload: { url: "/x", method: "PUT", headers: {}, expires_at: "" } })),
      uploadVideo: vi.fn(async () => {}),
      startAnalysis: vi.fn(async () => ({ id: "a1", status: "queued" })),
    };
    const file = new File(["x"], "serve.mov", { type: "video/quicktime" });
    await runUpload(client as never, { file, hand: "right", contentType: "video/quicktime", cameraView: "behind" });
    expect(client.createAnalysis).toHaveBeenCalledWith(expect.objectContaining({ camera_view: "behind" }));
  });
});
