import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";

import { LEGAL } from "./config";
import { PrivacyPage, TermsPage } from "./LegalPages";

const renderPage = (page: React.ReactNode) => render(<MemoryRouter>{page}</MemoryRouter>);

describe("legal pages", () => {
  it("states the retention periods the app actually uses", () => {
    renderPage(<PrivacyPage />);
    expect(screen.getByRole("heading", { name: "Privacy Policy" })).toBeInTheDocument();
    expect(screen.getByText(/deleted automatically 30 days after upload/)).toBeInTheDocument();
    expect(screen.getByText(/Uploads that never finished:/).parentElement).toHaveTextContent("deleted after 1 day");
    expect(screen.getByText(/We don't use your videos to train/)).toBeInTheDocument();
    expect(LEGAL.uploadRetentionDays).toBe(30); // keep in step with SERVE_API_UPLOAD_RETENTION_DAYS
  });

  it("covers age, ownership and the analysis' limits in the terms", () => {
    renderPage(<TermsPage />);
    expect(screen.getByText(/You must be at least 13/)).toBeInTheDocument();
    expect(screen.getByText("You keep ownership of everything you upload.")).toBeInTheDocument();
    expect(screen.getByText(/isn't medical or physiotherapy advice/)).toBeInTheDocument();
  });
});
