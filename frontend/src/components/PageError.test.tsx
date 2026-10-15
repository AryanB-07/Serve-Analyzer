import { render, screen } from "@testing-library/react";
import { createMemoryRouter, Outlet } from "react-router";
import { RouterProvider } from "react-router/dom";
import { expect, it, vi } from "vitest";

import { PageError } from "./PageError";

function Boom(): never {
  throw new Error("a field the page didn't expect");
}

it("shows a friendly page inside the shell when a page crashes", async () => {
  const quiet = vi.spyOn(console, "error").mockImplementation(() => {});
  const router = createMemoryRouter(
    [{
      element: <><nav aria-label="Main">nav</nav><Outlet /></>,
      children: [{ errorElement: <PageError />, children: [{ path: "/boom", element: <Boom /> }] }],
    }],
    { initialEntries: ["/boom"] },
  );
  render(<RouterProvider router={router} />);
  expect(await screen.findByRole("heading", { name: "Something went wrong showing this page" })).toBeInTheDocument();
  expect(screen.getByRole("navigation", { name: "Main" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Reload" })).toBeInTheDocument();
  expect(quiet).toHaveBeenCalledWith("page crashed", expect.any(Error));
  quiet.mockRestore();
});
