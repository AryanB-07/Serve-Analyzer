import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from ".";

export const friendsKeys = {
  connections: ["connections"] as const,
  count: ["connections", "count"] as const,
  person: (username: string) => ["person", username.toLowerCase()] as const,
  blocks: ["blocks"] as const,
  leaderboard: ["leaderboard"] as const,
};

export function useConnections() {
  return useQuery({ queryKey: friendsKeys.connections, queryFn: () => api.listConnections() });
}

/** Requests waiting for you, for the navigation's badge: checked every minute and on focus. */
export function useRequestCount(enabled = true) {
  return useQuery({ queryKey: friendsKeys.count, queryFn: () => api.countRequests(), enabled, refetchInterval: 60_000 });
}

/** Someone's page. A 404 (no one, or a block) isn't retried. */
export function usePerson(username: string) {
  return useQuery({
    queryKey: friendsKeys.person(username),
    queryFn: () => api.getPerson(username),
    retry: (count, error) => !(error instanceof Error && "status" in error && (error as { status: number }).status === 404) && count < 2,
  });
}

export function useLeaderboard() {
  return useQuery({ queryKey: friendsKeys.leaderboard, queryFn: () => api.getLeaderboard() });
}

export function useBlocks() {
  return useQuery({ queryKey: friendsKeys.blocks, queryFn: () => api.listBlocks() });
}

/** After any change between you and someone: their page, your lists and the badge are refetched. */
function useFriendsMutation<T>(run: (arg: T) => Promise<unknown>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: run,
    onSettled: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: friendsKeys.connections }),
        queryClient.invalidateQueries({ queryKey: ["person"] }),
        queryClient.invalidateQueries({ queryKey: friendsKeys.blocks }),
        queryClient.invalidateQueries({ queryKey: friendsKeys.leaderboard }),
      ]),
  });
}

export const useSendRequest = () => useFriendsMutation((username: string) => api.sendRequest(username));
export const useAcceptRequest = () => useFriendsMutation((id: string) => api.acceptRequest(id));
export const useRemoveConnection = () => useFriendsMutation((id: string) => api.removeConnection(id));
export const useBlock = () => useFriendsMutation((username: string) => api.block(username));
export const useUnblock = () => useFriendsMutation((username: string) => api.unblock(username));
