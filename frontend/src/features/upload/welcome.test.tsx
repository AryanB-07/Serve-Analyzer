/** The first-visit walkthrough on the upload page. */
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AnalysisList } from "../../api/types";

const fake = vi.hoisted(() => ({ getMe: vi.fn(), listAnalyses: vi.fn() }));

vi.mock("../../api", async () => {
  const client = await import("../../api/client");
  return { api: fake, USE_MOCKS: false, ApiError: client.ApiError, UploadAbortedError: client.UploadAbortedError };
});

const { createQueryClient } = await import("../../api/session");
const { DISMISSED_KEY, Welcome } = await import("./Welcome");
const { FilmingGuide } = await import("./FilmingGuide");

const EMPTY: AnalysisList = { items: [], next_cursor: null };

beforeEach(() => {
  window.localStorage.clear();
  fake.getMe.mockReset().mockResolvedValue(null);
  fake.listAnalyses.mockReset().mockResolvedValue(EMPTY);
});

function renderWelcome() {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <Welcome />
        <FilmingGuide />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("the first-visit walkthrough", () => {
  it("shows the three steps to someone with no analyses yet", async () => {
    renderWelcome();
    expect(await screen.findByRole("heading", { name: /Your first analysis in three steps/ })).toBeInTheDocument();
    expect(screen.getByText("Film one serve, side-on")).toBeInTheDocument();
    expect(screen.getByText("Choose your hand and upload")).toBeInTheDocument();
    expect(screen.getByText("Step through it frame by frame")).toBeInTheDocument();
  });

  it("says where to find it again once dismissed", async () => {
    renderWelcome();
    const card = (await screen.findByRole("heading", { name: /three steps/ })).closest("section")!;
    expect(card).toHaveTextContent("This guide stays in Help: the ?question mark button at the top of every page.");
  });

  it("takes you to the filming guide", async () => {
    const scroll = vi.fn();
    Element.prototype.scrollIntoView = scroll;
    renderWelcome();
    await userEvent.click(await screen.findByRole("button", { name: "Show me how to film it" }));
    expect(scroll).toHaveBeenCalledTimes(1);
    expect(document.activeElement).toBe(screen.getByRole("region", { name: "How to film your serve" }));
  });

  it("stays dismissed", async () => {
    const { unmount } = renderWelcome();
    await userEvent.click(await screen.findByRole("button", { name: "Got it" }));
    expect(screen.queryByRole("heading", { name: /three steps/ })).not.toBeInTheDocument();
    expect(window.localStorage.getItem(DISMISSED_KEY)).toBe("1");
    unmount();
    renderWelcome();
    await screen.findByRole("heading", { name: "How to film your serve" });
    expect(fake.listAnalyses).toHaveBeenCalled();
    expect(screen.queryByRole("heading", { name: /three steps/ })).not.toBeInTheDocument();
  });

  it("can be closed with the dismiss button", async () => {
    renderWelcome();
    await userEvent.click(await screen.findByRole("button", { name: "Dismiss the welcome guide" }));
    expect(screen.queryByRole("heading", { name: /three steps/ })).not.toBeInTheDocument();
  });

  it("isn't shown once you have analyses", async () => {
    fake.listAnalyses.mockResolvedValue({
      items: [{ id: "a", hand: "right", status: "succeeded", filename: "a.mp4", created_at: "", updated_at: "" }],
      next_cursor: null,
    });
    renderWelcome();
    await vi.waitFor(() => expect(fake.listAnalyses).toHaveBeenCalled());
    await screen.findByRole("heading", { name: "How to film your serve" });
    expect(screen.queryByRole("heading", { name: /three steps/ })).not.toBeInTheDocument();
  });

  it("still works when storage is blocked", async () => {
    const getItem = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    const setItem = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    renderWelcome();
    await userEvent.click(await screen.findByRole("button", { name: "Got it" }));
    expect(screen.queryByRole("heading", { name: /three steps/ })).not.toBeInTheDocument();
    getItem.mockRestore();
    setItem.mockRestore();
  });
});
