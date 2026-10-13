import { QueryClient, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { setUnauthorizedHandler } from "./client";
import { shouldRetry } from "./retry";
import type { Credentials, SignupRequest, User } from "./types";
import { api } from ".";

export const sessionKey = ["session"] as const;

/** The app's query client. A 401 on any data request marks the session as signed out. */
export function createQueryClient(): QueryClient {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: shouldRetry, refetchOnWindowFocus: false },
    },
  });
  setUnauthorizedHandler(() => client.setQueryData<User | null>(sessionKey, null));
  return client;
}

/** The signed-in user (null when signed out). Pending until the first check finishes. */
export function useSession() {
  return useQuery({
    queryKey: sessionKey,
    queryFn: () => api.getMe(),
    staleTime: 5 * 60_000,
  });
}

/**
 * Drop every cached query and record the new session, so nothing one user
 * loaded is ever shown to the next person on the same browser.
 */
function useSwitchUser() {
  const queryClient = useQueryClient();
  return (user: User | null) => {
    // The session query itself is updated in place: removing it would leave
    // mounted components (like the header) watching a query that no longer exists.
    queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== sessionKey[0] });
    queryClient.setQueryData<User | null>(sessionKey, user);
  };
}

export function useLogIn() {
  const switchUser = useSwitchUser();
  return useMutation({
    mutationFn: (body: Credentials) => api.logIn(body),
    onSuccess: switchUser,
  });
}

export function useSignUp() {
  const switchUser = useSwitchUser();
  return useMutation({
    mutationFn: (body: SignupRequest) => api.signUp(body),
    onSuccess: switchUser,
  });
}

/**
 * ``onSignedOut`` runs before the session is cleared, so the page can leave the signed-in
 * routes first. (Otherwise the route guard's redirect to /login?next=… races it.)
 */
export function useLogOut(onSignedOut?: () => void) {
  const switchUser = useSwitchUser();
  return useMutation({
    mutationFn: () => api.logOut(),
    // Signed out locally even if the request failed: the user asked to leave.
    onSettled: () => {
      onSignedOut?.();
      switchUser(null);
    },
  });
}

/** Confirming an email updates the signed-in user, if this browser is signed in. */
export function useVerifyEmail() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (token: string) => api.verifyEmail(token),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: sessionKey }),
  });
}

export function useResendVerification() {
  return useMutation({ mutationFn: () => api.resendVerification() });
}

export function useRequestPasswordReset() {
  return useMutation({ mutationFn: (email: string) => api.requestPasswordReset(email) });
}

/** A reset signs out every device, this one included. */
export function useResetPassword() {
  const switchUser = useSwitchUser();
  return useMutation({
    mutationFn: ({ token, password }: { token: string; password: string }) => api.resetPassword(token, password),
    onSuccess: () => switchUser(null),
  });
}

/**
 * ``onDeleted`` runs before the session is cleared, so it can leave the signed-in
 * pages first (otherwise the route guard would send the user to sign in).
 */
export function useDeleteAccount(onDeleted: () => void) {
  const switchUser = useSwitchUser();
  return useMutation({
    mutationFn: (password: string) => api.deleteAccount(password),
    onSuccess: () => {
      onDeleted();
      switchUser(null);
    },
  });
}

export function useRequestEmailChange() {
  return useMutation({
    mutationFn: ({ newEmail, password }: { newEmail: string; password: string }) =>
      api.requestEmailChange(newEmail, password),
  });
}

/** Confirming the new address updates the signed-in user, if this browser is signed in. */
export function useConfirmEmailChange() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (token: string) => api.confirmEmailChange(token),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: sessionKey }),
  });
}

/** The export's file name, dated like the server's: serve-analyzer-data-2026-10-12.json. */
export function exportFilename(exportedAt: string): string {
  return `serve-analyzer-data-${exportedAt.slice(0, 10)}.json`;
}

/** Fetch everything stored about the account and save it as a JSON file. */
export function useDownloadData() {
  return useMutation({
    mutationFn: async () => {
      const data = await api.exportData();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = exportFilename(data.exported_at);
      document.body.append(link);
      link.click();
      link.remove();
      // Revoked on the next tick: some browsers start the download asynchronously.
      setTimeout(() => URL.revokeObjectURL(url), 0);
      return data;
    },
  });
}
