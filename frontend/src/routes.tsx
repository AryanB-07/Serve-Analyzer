import { createBrowserRouter, Link, Navigate, useLocation } from "react-router";

import { AppShell } from "./components/AppShell";
import { PageError } from "./components/PageError";
import {
  AccountDeletedPage,
  SettingsPage,
  ConfirmEmailChangePage,
  ForgotPasswordPage,
  ResetPasswordPage,
  VerifyEmailPage,
} from "./features/account/AccountPages";
import { LoginPage, SignupPage } from "./features/auth/AuthPages";
import { RequireAuth } from "./features/auth/RequireAuth";
import { ComparePage } from "./features/compare/ComparePage";
import { DemoPage } from "./features/demo/DemoPage";
import { FriendsPage } from "./features/friends/FriendsPage";
import { PersonPage } from "./features/friends/PersonPage";
import { HistoryPage } from "./features/history/HistoryPage";
import { PrivacyPage, TermsPage } from "./features/legal/LegalPages";
import { ProfilePage } from "./features/profile/ProfilePage";
import { ResultsPage } from "./features/results/ResultsPage";
import { UploadPage } from "./features/upload/UploadPage";

/** An old address (a bookmark, an emailed link) kept working, with its query string. */
function Moved({ to }: { to: string }) {
  const { search, hash } = useLocation();
  return <Navigate to={`${to}${search}${hash}`} replace />;
}

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
    errorElement: <PageError />, // the shell itself failed
    children: [
      {
        // A page that crashes shows PageError inside the shell.
        errorElement: <PageError />,
        children: [
          { path: "/login", element: <LoginPage /> },
          { path: "/signup", element: <SignupPage /> },
          { path: "/forgot-password", element: <ForgotPasswordPage /> },
          { path: "/reset-password", element: <ResetPasswordPage /> },
          { path: "/verify-email", element: <VerifyEmailPage /> },
          { path: "/confirm-email", element: <ConfirmEmailChangePage /> },
          { path: "/account-deleted", element: <AccountDeletedPage /> },
          { path: "/privacy", element: <PrivacyPage /> },
          { path: "/terms", element: <TermsPage /> },
          { path: "/demo", element: <DemoPage /> },
          {
            element: <RequireAuth />,
            children: [
              { path: "/", element: <UploadPage /> },
              { path: "/analyses/:id", element: <ResultsPage /> },
              { path: "/serves", element: <HistoryPage /> },
              { path: "/history", element: <Moved to="/serves" /> },
              { path: "/compare", element: <ComparePage /> },
              { path: "/profile", element: <ProfilePage /> },
              { path: "/friends", element: <FriendsPage /> },
              { path: "/u/:username", element: <PersonPage /> },
              { path: "/settings", element: <SettingsPage /> },
              { path: "/account", element: <Moved to="/settings" /> },
            ],
          },
          { path: "*", element: <NotFound /> },
        ],
      },
    ],
  },
];

export const router = createBrowserRouter(routes);
