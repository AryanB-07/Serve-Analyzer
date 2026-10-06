import { createBrowserRouter, Link } from "react-router";

import { AppShell } from "./components/AppShell";
import {
  AccountDeletedPage,
  AccountPage,
  ForgotPasswordPage,
  ResetPasswordPage,
  VerifyEmailPage,
} from "./features/account/AccountPages";
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
      { path: "/forgot-password", element: <ForgotPasswordPage /> },
      { path: "/reset-password", element: <ResetPasswordPage /> },
      { path: "/verify-email", element: <VerifyEmailPage /> },
      { path: "/account-deleted", element: <AccountDeletedPage /> },
      {
        element: <RequireAuth />,
        children: [
          { path: "/", element: <UploadPage /> },
          { path: "/analyses/:id", element: <ResultsPage /> },
          { path: "/history", element: <HistoryPage /> },
          { path: "/compare", element: <ComparePage /> },
          { path: "/account", element: <AccountPage /> },
        ],
      },
      { path: "*", element: <NotFound /> },
    ],
  },
];

export const router = createBrowserRouter(routes);
