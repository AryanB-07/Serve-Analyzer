import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from ".";
import type { SendMessage, UserReportRequest } from "./types";

/**
 * Messages arrive by polling: every 5 s in an open conversation, every 15 s for the list and
 * 30 s for the badge. Plenty for conversations between friends on one small server; push
 * (server-sent events) would be the next step if it ever isn't.
 */
export const messageKeys = {
  list: ["conversations"] as const,
  unread: ["conversations", "unread"] as const,
  conversation: (id: string) => ["conversation", id] as const,
  messages: (id: string) => ["messages", id] as const,
};

const notFound = (error: unknown) =>
  error instanceof Error && "status" in error && (error as { status: number }).status === 404;

export function useConversations() {
  return useQuery({ queryKey: messageKeys.list, queryFn: () => api.listConversations(), refetchInterval: 15_000 });
}

export function useUnreadCount(enabled = true) {
  return useQuery({ queryKey: messageKeys.unread, queryFn: () => api.countUnread(), enabled, refetchInterval: 30_000 });
}

export function useConversation(id: string) {
  return useQuery({
    queryKey: messageKeys.conversation(id),
    queryFn: () => api.getConversation(id),
    retry: (count, error) => !notFound(error) && count < 2,
  });
}

export function useMessages(id: string) {
  return useInfiniteQuery({
    queryKey: messageKeys.messages(id),
    queryFn: ({ pageParam }) => api.listMessages(id, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    refetchInterval: 5_000,
    retry: (count, error) => !notFound(error) && count < 2,
  });
}

function useRefreshAfter<T, R>(run: (arg: T) => Promise<R>, id?: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: run,
    onSettled: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: messageKeys.list }),
        ...(id ? [queryClient.invalidateQueries({ queryKey: messageKeys.messages(id) })] : []),
      ]),
  });
}

export const useSendMessage = (id: string) => useRefreshAfter((message: SendMessage) => api.sendMessage(id, message), id);
export const useDeleteMessage = (id: string) => useRefreshAfter((messageId: string) => api.deleteMessage(messageId), id);
export const useStartConversation = () => useRefreshAfter((username: string) => api.startConversation(username));

export function useMarkRead(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.markRead(id),
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: messageKeys.unread }),
        queryClient.invalidateQueries({ queryKey: messageKeys.list }),
      ]),
  });
}

export function useReport() {
  return useMutation({ mutationFn: (body: UserReportRequest) => api.report(body) });
}
