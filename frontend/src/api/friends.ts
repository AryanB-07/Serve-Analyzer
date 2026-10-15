import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from ".";

export const friendsKeys = {
  follows: ["follows"] as const,
  person: (username: string) => ["person", username.toLowerCase()] as const,
  blocks: ["blocks"] as const,
  leaderboard: ["leaderboard"] as const,
};

/** Your friends, followers and following, with counts. */
export function useFollows() {
  return useQuery({ queryKey: friendsKeys.follows, queryFn: () => api.listFollows() });
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
        queryClient.invalidateQueries({ queryKey: friendsKeys.follows }),
        queryClient.invalidateQueries({ queryKey: ["person"] }),
        queryClient.invalidateQueries({ queryKey: friendsKeys.blocks }),
        queryClient.invalidateQueries({ queryKey: friendsKeys.leaderboard }),
      ]),
  });
}

export const useFollow = () => useFriendsMutation((username: string) => api.follow(username));
export const useUnfollow = () => useFriendsMutation((username: string) => api.unfollow(username));
export const useRemoveFollower = () => useFriendsMutation((username: string) => api.removeFollower(username));
export const useBlock = () => useFriendsMutation((username: string) => api.block(username));
export const useUnblock = () => useFriendsMutation((username: string) => api.unblock(username));
