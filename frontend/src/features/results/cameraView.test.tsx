/** What the results show once someone has said where their camera was. */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter } from "react-router";
import { RouterProvider } from "react-router/dom";
import { describe, expect, it } from "vitest";

import type { AnalysisResult } from "../../api/types";
import { readingFor } from "../../lib/metricInfo";
import { joinList, measurementName, measurementsWith, readableLabels } from "../../lib/quality";
import { makeResult } from "../../test/fixtures";
import { renderWithPlayhead } from "../../test/playhead";
import { HelpProvider } from "../help/HelpProvider";
import { CameraNote } from "./CameraNote";
import { MetricCard, MetricCards, UNREADABLE_TEXT } from "./MetricCards";

const FRONT_QUALITY = {
  trophy: { front_knee_flexion: "approximate", back_knee_flexion: "approximate", elbow_angle: "unreadable", trunk_tilt: "approximate" },
  racket_drop: { elbow_angle: "approximate", trunk_tilt: "measured" },
  contact: { elbow_angle: "measured", wrist_height: "measured", front_knee_flexion: "measured", trunk_tilt: "measured" },
};

function filmed(view: string, quality: object): AnalysisResult {
  return { ...makeResult(), camera_view: view, quality } as unknown as AnalysisResult;
}

function renderNote(result: AnalysisResult) {
  const router = createMemoryRouter(
    [{ path: "*", element: <HelpProvider><CameraNote result={result} /></HelpProvider> }],
    { initialEntries: ["/analyses/a1"] },
  );
  render(<RouterProvider router={router} />);
  return router;
}

describe("the camera note", () => {
  it("says what the chosen position can't read and what's approximate", () => {
    renderNote(filmed("front", FRONT_QUALITY));
    const note = screen.getByRole("region", { name: "Filmed from across the net" });
    expect(note).toHaveTextContent(
      "From here, the elbow bend at the trophy position can't be read from one camera, so it isn't scored and has no feedback.",
    );
    expect(note).toHaveTextContent(
      "The front knee bend at the trophy position, back knee bend at the trophy position, trunk tilt at the trophy position and elbow bend in the racket drop are approximate from this angle.",
    );
  });

  it("leaves the approximate list to the cards in simple mode", () => {
    const router = createMemoryRouter(
      [{ path: "*", element: <HelpProvider><CameraNote result={filmed("front", FRONT_QUALITY)} mode="simple" /></HelpProvider> }],
      { initialEntries: ["/analyses/a1"] },
    );
    render(<RouterProvider router={router} />);
    const note = screen.getByRole("region", { name: "Filmed from across the net" });
    expect(note).toHaveTextContent("can't be read from one camera");
    expect(note).not.toHaveTextContent("approximate");
  });

  it("points to the filming guide from a position that loses measurements", async () => {
    const router = renderNote(filmed("front", FRONT_QUALITY));
    await userEvent.click(screen.getByRole("button", { name: "Where to put the camera" }));
    expect(new URLSearchParams(router.state.location.search).get("help")).toBe("filming");
  });

  it("doesn't send someone who filmed as the guide says back to the guide", () => {
    renderNote(filmed("side_hitting", { trophy: { elbow_angle: "unreadable" } }));
    expect(screen.getByRole("region", { name: "Filmed side-on, from your hitting-arm side" })).toHaveTextContent(
      "the elbow bend at the trophy position can't be read",
    );
    expect(screen.queryByRole("button", { name: "Where to put the camera" })).not.toBeInTheDocument();
  });

  it("says so when everything reads well", () => {
    renderNote(filmed("behind_diagonal_hitting", { contact: { wrist_height: "measured" } }));
    expect(screen.getByText("Every measurement reads well from this position.")).toBeInTheDocument();
  });

  it("gives a tip when nobody said where the camera was", () => {
    renderNote(makeResult());
    expect(screen.getByTestId("camera-tip")).toHaveTextContent("say where your camera was when you upload");
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
  });
});

describe("the measurement cards", () => {
  it("replace an unreadable measurement's number with why", () => {
    const result = filmed("behind_diagonal_toss", { trophy: { front_knee_flexion: "unreadable" } });
    renderWithPlayhead(<MetricCard reading={readingFor("front_knee_flexion", result)} phases={result.phases} />);
    const card = screen.getByRole("article", { name: "Front knee bend" });
    expect(within(card).getByTestId("metric-status")).toHaveTextContent(UNREADABLE_TEXT);
    expect(within(card).queryByText(/86/)).not.toBeInTheDocument();
    expect(within(card).queryByText(/Good range/)).not.toBeInTheDocument();
    expect(card).toHaveTextContent("can't see this clearly enough to score it");
  });

  it("mark an approximate measurement but still show it", () => {
    const result = filmed("front", FRONT_QUALITY);
    renderWithPlayhead(<MetricCard reading={readingFor("front_knee_flexion", result)} phases={result.phases} />);
    const card = screen.getByRole("article", { name: "Front knee bend" });
    expect(card).toHaveTextContent("≈86.2°");
    expect(within(card).getByText("approximate from this angle")).toBeInTheDocument();
    expect(within(card).getByTestId("metric-status")).toHaveTextContent("Borderline: a little high");
  });

  it("show the camera note with them, without a help dialog nearby", () => {
    renderWithPlayhead(<MetricCards result={filmed("front", FRONT_QUALITY)} />);
    expect(screen.getByRole("region", { name: "Filmed from across the net" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Where to put the camera" })).not.toBeInTheDocument();
  });
});

describe("quality helpers", () => {
  it("name measurements in plain words and list them", () => {
    expect(measurementName("contact", "wrist_height")).toBe("contact height");
    expect(joinList(["a"])).toBe("a");
    expect(joinList(["a", "b"])).toBe("a and b");
    expect(joinList(["a", "b", "c"])).toBe("a, b and c");
  });

  it("drop the verdict of unreadable measurements from the skeleton colours, and nothing else", () => {
    const result = filmed("behind_diagonal_toss", { trophy: { front_knee_flexion: "unreadable", trunk_tilt: "measured" } });
    expect(result.labels.trophy.front_knee_flexion).toBe("borderline");
    const labels = readableLabels(result);
    expect(labels.trophy.front_knee_flexion).toBe("unknown");
    expect(labels.trophy.trunk_tilt).toBe(result.labels.trophy.trunk_tilt);
    expect(result.labels.trophy.front_knee_flexion).toBe("borderline"); // the original isn't changed
    const plain = makeResult();
    expect(readableLabels(plain)).toBe(plain.labels); // nothing to change without a camera position
    expect(measurementsWith(result, "unreadable")).toEqual([{ phase: "trophy", metric: "front_knee_flexion" }]);
  });
});
