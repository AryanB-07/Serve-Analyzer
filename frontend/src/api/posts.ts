import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from ".";
import type { CreatePost, EditPost, FeedTab, LikeState, Post } from "./types";

export const postKeys = {
  all: ["posts"] as const,
  post: (id: string) => ["posts", "one", id] as const,
  by: (username: string) => ["posts", "by", username] as const,
  feed: (tab: FeedTab) => ["posts", "feed", tab] as const,
  comments: (id: string) => ["posts", "comments", id] as const,
};

const notFound = (error: unknown) =>
  error instanceof Error && "status" in error && (error as { status: number }).status === 404;

export function usePost(id: string) {
  return useQuery({ queryKey: postKeys.post(id), queryFn: () => api.getPost(id), retry: (n, e) => !notFound(e) && n < 2 });
}

/** Someone's posts that you can see, a page at a time. */
export function usePostsBy(username: string | null | undefined) {
  return useInfiniteQuery({
    queryKey: postKeys.by(username ?? ""),
    queryFn: ({ pageParam }) => api.listPostsBy(username!, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    enabled: Boolean(username),
  });
}

/** A feed tab, a page at a time. */
export function useFeed(tab: FeedTab) {
  return useInfiniteQuery({
    queryKey: postKeys.feed(tab),
    queryFn: ({ pageParam }) => api.getFeed(tab, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
}

export function useComments(postId: string) {
  return useInfiniteQuery({
    queryKey: postKeys.comments(postId),
    queryFn: ({ pageParam }) => api.listComments(postId, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
}

function useRefreshPosts<T, R>(run: (arg: T) => Promise<R>) {
  const queryClient = useQueryClient();
  return useMutation({ mutationFn: run, onSettled: () => queryClient.invalidateQueries({ queryKey: postKeys.all }) });
}

export const useCreatePost = () => useRefreshPosts((body: CreatePost) => api.createPost(body));
export const useEditPost = (id: string) => useRefreshPosts((body: EditPost) => api.editPost(id, body));
/** The deleted post is dropped from the cache rather than refetched, which would only 404. */
export function useDeletePost() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deletePost(id),
    onSuccess: (_r, id) => {
      queryClient.removeQueries({ queryKey: postKeys.post(id) });
      queryClient.removeQueries({ queryKey: postKeys.comments(id) });
      return queryClient.invalidateQueries({ queryKey: postKeys.all });
    },
  });
}
export const useAddComment = (postId: string) => useRefreshPosts((body: string) => api.addComment(postId, body));
export const useDeleteComment = () => useRefreshPosts((id: string) => api.deleteComment(id));

/**
 * Like or unlike, shown at once: every cached copy of the post is updated before the server
 * answers, and put back if it refuses.
 */
export function useLike(post: Post) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (like: boolean) => (like ? api.like(post.id) : api.unlike(post.id)),
    onMutate: (like: boolean) => {
      const apply = (state: LikeState) => patchPost(queryClient, post.id, { liked_by_you: state.liked, like_count: state.like_count });
      const before = { liked: post.liked_by_you, like_count: post.like_count };
      apply({ liked: like, like_count: post.like_count + (like === post.liked_by_you ? 0 : like ? 1 : -1) });
      return { before, apply };
    },
    onError: (_e, _like, context) => context?.apply(context.before),
    onSuccess: (state) => patchPost(queryClient, post.id, { liked_by_you: state.liked, like_count: state.like_count }),
  });
}

function patchPost(queryClient: ReturnType<typeof useQueryClient>, id: string, patch: Partial<Post>) {
  queryClient.setQueriesData<unknown>({ queryKey: postKeys.all }, (data: unknown) => {
    if (!data || typeof data !== "object") return data;
    if ("id" in data && (data as Post).id === id) return { ...(data as Post), ...patch };
    if ("pages" in data) {
      const d = data as { pages: { items: Post[] }[] };
      return { ...d, pages: d.pages.map((p) => ({ ...p, items: p.items.map((x) => (x.id === id ? { ...x, ...patch } : x)) })) };
    }
    return data;
  });
}
