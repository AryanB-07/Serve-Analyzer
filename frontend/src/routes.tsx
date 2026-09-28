import { createBrowserRouter, Link } from "react-router";

import { AppShell } from "./components/AppShell";
import { LoginPage, SignupPage } from "./features/auth/AuthPages";
import { RequireAuth } from "./features/auth/RequireAuth";
import { ComparePage } from "./features/compare/ComparePage";
import { HistoryPage } from "./features/history/HistoryPage";
import { ResultsPage } from "./features/results/ResultsPage";
import { UploadPage } from "./features/upload/UploadPage";

function NotFound() {
  return (
    <div className="space-y-3">
      <h1 className="text-2xl font-semibold">Page not found</h1>
      <Link to="/" className="text-accent underline">Back to upload</Link>
    </div>
  );
}

export const routes = [
  {
    element: <AppShell />,
    children: [
      { path: "/login", element: <LoginPage /> },
      { path: "/signup", element: <SignupPage /> },
      {
        element: <RequireAuth />,
        children: [
          { path: "/", element: <UploadPage /> },
          { path: "/analyses/:id", element: <ResultsPage /> },
          { path: "/history", element: <HistoryPage /> },
          { path: "/compare", element: <ComparePage /> },
        ],
      },
      { path: "*", element: <NotFound /> },
    ],
  },
];

export const router = createBrowserRouter(routes);
