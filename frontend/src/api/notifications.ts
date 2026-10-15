import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from ".";

export const notificationKeys = { list: ["notifications"] as const, unread: ["notifications", "unread"] as const };

/** The bell's count: checked every minute and on focus. */
export function useNotificationCount(enabled = true) {
  return useQuery({ queryKey: notificationKeys.unread, queryFn: () => api.countNotifications(), enabled, refetchInterval: 60_000 });
}

export function useNotifications(enabled: boolean) {
  return useQuery({ queryKey: notificationKeys.list, queryFn: () => api.listNotifications(), enabled });
}

export function useMarkNotificationsRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.markNotificationsRead(),
    onSuccess: () => {
      queryClient.setQueryData(notificationKeys.unread, 0);
    },
  });
}
