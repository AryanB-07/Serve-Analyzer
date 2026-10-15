import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from ".";
import type { Profile, ProfileUpdate } from "./types";

export const profileKey = ["profile"] as const;

/** Your profile, with its stats. Cleared on sign-out with every other query (session.ts). */
export function useProfile(enabled = true) {
  return useQuery({ queryKey: profileKey, queryFn: () => api.getProfile(), enabled });
}

function useSaveProfile<T>(save: (arg: T) => Promise<Profile>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: save,
    onSuccess: (profile) => queryClient.setQueryData(profileKey, profile),
  });
}

export const useUpdateProfile = () => useSaveProfile((body: ProfileUpdate) => api.updateProfile(body));
export const useSetAvatar = () => useSaveProfile((jpeg: Blob) => api.setAvatar(jpeg));
export const useRemoveAvatar = () => useSaveProfile(() => api.removeAvatar());

/** Whether ``username`` could be yours. Pass null to skip (empty, or already known to be invalid). */
export function useUsernameCheck(username: string | null, signedOut = false) {
  return useQuery({
    queryKey: ["username-check", username, signedOut] as const,
    queryFn: () => (signedOut ? api.checkUsernameForSignup(username!) : api.checkUsername(username!)),
    enabled: username !== null,
    staleTime: 30_000,
  });
}

export function useChangePassword() {
  return useMutation({
    mutationFn: ({ current, next }: { current: string; next: string }) => api.changePassword(current, next),
  });
}
