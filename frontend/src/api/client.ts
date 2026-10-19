import type {
  AnalysisList,
  AnalysisResult,
  AnalysisSummary,
  BlockedPerson,
  Comment,
  CommentPage,
  ConversationSummary,
  CreatePost,
  CreateAnalysisRequest,
  CreateAnalysisResponse,
  Credentials,
  DataExport,
  EditPost,
  FollowCounts,
  FollowListKind,
  FollowPage,
  FramesPayload,
  Leaderboard,
  LikeState,
  Message,
  MessagePage,
  Notification,
  Person,
  Post,
  FeedTab,
  PostPage,
  ReceivedServePage,
  Profile,
  ProfileUpdate,
  Report,
  ReportRequest,
  SendMessage,
  SignupRequest,
  UploadTarget,
  User,
  UsernameCheck,
  UserReportRequest,
} from "./types";
import { demoFile, isDemoId } from "./demo";

/** Everything the UI needs from the backend. Implemented over HTTP and by the mock. */
export interface ApiClient {
  /** The signed-in user, or null when there is no valid session. */
  getMe(): Promise<User | null>;
  signUp(body: SignupRequest): Promise<User>;
  logIn(body: Credentials): Promise<User>;
  logOut(): Promise<void>;
  /** Confirm an email address with the token from the emailed link. */
  verifyEmail(token: string): Promise<void>;
  resendVerification(): Promise<void>;
  /** Always resolves (the server answers the same whether or not the address has an account). */
  requestPasswordReset(email: string): Promise<void>;
  resetPassword(token: string, password: string): Promise<void>;
  /** Permanently delete the signed-in account and everything in it. */
  deleteAccount(password: string): Promise<void>;
  /** Email a confirmation link to ``newEmail``; the account keeps its address until it's opened. */
  requestEmailChange(newEmail: string, password: string): Promise<void>;
  confirmEmailChange(token: string): Promise<void>;
  /** Everything stored about the signed-in account. */
  exportData(): Promise<DataExport>;
  /** The report sent about an analysis ("this result looks wrong"), or null. */
  getReport(id: string): Promise<Report | null>;
  reportAnalysis(id: string, body: ReportRequest): Promise<Report>;
  deleteAnalysis(id: string): Promise<void>;
  createAnalysis(body: CreateAnalysisRequest): Promise<CreateAnalysisResponse>;
  uploadVideo(
    target: UploadTarget,
    file: Blob,
    onProgress: (fraction: number) => void,
    signal?: AbortSignal,
  ): Promise<void>;
  startAnalysis(id: string): Promise<AnalysisSummary>;
  retryAnalysis(id: string): Promise<AnalysisSummary>;
  getAnalysis(id: string): Promise<AnalysisSummary>;
  /** History, newest first. ``query`` is History's filters as API parameters (lib/historyFilters). */
  listAnalyses(cursor?: string, query?: Record<string, string>): Promise<AnalysisList>;
  /** Add, change or (with an empty note) remove your note on an analysis. */
  setNote(id: string, note: string): Promise<AnalysisSummary>;
  getResult(id: string): Promise<AnalysisResult>;
  getFrames(id: string): Promise<FramesPayload>;
  getProfile(): Promise<Profile>;
  /** Change only the fields given; an empty display name or bio removes it. */
  updateProfile(body: ProfileUpdate): Promise<Profile>;
  checkUsername(username: string): Promise<UsernameCheck>;
  /** A new profile picture, already cropped and shrunk to a JPEG (lib/avatar). */
  setAvatar(jpeg: Blob): Promise<Profile>;
  removeAvatar(): Promise<Profile>;
  /** Keeps this device signed in and signs out every other one. */
  changePassword(currentPassword: string, newPassword: string): Promise<void>;
  /** Someone's page by username; 404 if there's no one (or a block either way). */
  getPerson(username: string): Promise<Person>;
  /** How many friends (people who follow each other with you), followers and following you have. */
  getFollowCounts(): Promise<FollowCounts>;
  /** A page of someone's friends, followers or following: only they and their friends can see these. */
  listFollowPage(username: string, kind: FollowListKind, cursor?: string): Promise<FollowPage>;
  /** For the signup form: whether a username is free (no account needed). */
  checkUsernameForSignup(username: string): Promise<UsernameCheck>;
  /** Follow someone, or follow them back. Doing it twice is harmless. */
  follow(username: string): Promise<Person>;
  /** Stop following; ends a friendship. Harmless if you weren't following. */
  unfollow(username: string): Promise<void>;
  /** Remove someone from your followers. */
  removeFollower(username: string): Promise<void>;
  listBlocks(): Promise<BlockedPerson[]>;
  /** You and your friends who joined it, ranked. */
  getLeaderboard(): Promise<Leaderboard>;
  listConversations(): Promise<ConversationSummary[]>;
  countUnread(): Promise<number>;
  /** Serves friends sent you, newest first. Opening one (getAnalysis) marks it seen. */
  listReceived(cursor?: string): Promise<ReceivedServePage>;
  /** Received serves you haven't opened and still can. */
  countUnseenServes(): Promise<number>;
  /** Open (or make) your conversation with a friend. */
  startConversation(username: string): Promise<ConversationSummary>;
  getConversation(id: string): Promise<ConversationSummary>;
  /** Newest first; ``before`` is the previous page's next_cursor. */
  listMessages(id: string, before?: string): Promise<MessagePage>;
  /** Text, one of your finished serves, or both. */
  sendMessage(id: string, message: SendMessage): Promise<Message>;
  markRead(id: string): Promise<void>;
  deleteMessage(messageId: string): Promise<void>;
  /** Report a person, or one of their messages to you. */
  report(body: UserReportRequest): Promise<void>;
  /** Post one of your finished serves (a snapshot: video, thumbnail and scores). */
  createPost(body: CreatePost): Promise<Post>;
  getPost(id: string): Promise<Post>;
  editPost(id: string, body: EditPost): Promise<Post>;
  deletePost(id: string): Promise<void>;
  /** Someone's posts that you can see, newest first. */
  listPostsBy(username: string, cursor?: string): Promise<PostPage>;
  /** Public: everyone's public posts. Friends: your friends' posts. Newest first. */
  getFeed(tab: FeedTab, cursor?: string): Promise<PostPage>;
  like(postId: string): Promise<LikeState>;
  unlike(postId: string): Promise<LikeState>;
  /** Oldest first. */
  listComments(postId: string, cursor?: string): Promise<CommentPage>;
  addComment(postId: string, body: string): Promise<Comment>;
  deleteComment(commentId: string): Promise<void>;
  listNotifications(): Promise<Notification[]>;
  countNotifications(): Promise<number>;
  markNotificationsRead(): Promise<void>;
  block(username: string): Promise<void>;
  unblock(username: string): Promise<void>;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export class UploadAbortedError extends Error {
  constructor() {
    super("Upload cancelled");
    this.name = "UploadAbortedError";
  }
}

const BASE = "/api";

let onUnauthorized: () => void = () => {};

/**
 * Called when a data request is refused with 401, i.e. the session has expired
 * or been revoked. (A 401 from the auth endpoints themselves means a wrong
 * password or no session yet, and is left to the caller.)
 */
export function setUnauthorizedHandler(handler: () => void): void {
  onUnauthorized = handler;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (res.status === 401 && !path.startsWith("/auth/")) onUnauthorized();
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
      // A validation error (422) lists what's wrong: show the first problem, in plain words.
      const first = Array.isArray(body.detail) ? (body.detail[0] as { msg?: unknown } | undefined) : undefined;
      if (typeof first?.msg === "string") detail = first.msg.replace(/^Value error, /, "");
    } catch {
      // Non-JSON error body: keep the status text.
    }
    throw new ApiError(res.status, detail);
  }
  // 202 Accepted and 204 No Content come back with no body.
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

/** fetch() cannot report upload progress, so the PUT uses XMLHttpRequest. */
export function putWithProgress(
  target: UploadTarget,
  file: Blob,
  onProgress: (fraction: number) => void,
  signal?: AbortSignal,
): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(new UploadAbortedError());
    const xhr = new XMLHttpRequest();
    xhr.open(target.method, target.url);
    for (const [name, value] of Object.entries(target.headers)) xhr.setRequestHeader(name, value);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(e.loaded / e.total);
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        onProgress(1);
        resolve();
      } else {
        reject(new ApiError(xhr.status, `Upload failed (${xhr.status})`));
      }
    };
    xhr.onerror = () => reject(new ApiError(0, "Network error during upload"));
    xhr.onabort = () => reject(new UploadAbortedError());
    signal?.addEventListener("abort", () => xhr.abort(), { once: true });
    xhr.send(file);
  });
}

/** A demo analysis's static file (see demo.ts), fetched without the API or a session. */
async function demo<T>(id: string, file: Parameters<typeof demoFile>[1]): Promise<T> {
  const res = await fetch(demoFile(id, file));
  if (!res.ok) throw new ApiError(res.status, "Demo analysis not found");
  return (await res.json()) as T;
}

export const httpClient: ApiClient = {
  getMe: async () => {
    try {
      return await request<User>("/auth/me");
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) return null;
      throw error;
    }
  },
  signUp: (body) => request("/auth/signup", { method: "POST", body: JSON.stringify(body) }),
  logIn: (body) => request("/auth/login", { method: "POST", body: JSON.stringify(body) }),
  logOut: () => request("/auth/logout", { method: "POST" }),
  verifyEmail: (token) => request("/auth/verify-email", { method: "POST", body: JSON.stringify({ token }) }),
  resendVerification: () => request("/auth/verify-email/resend", { method: "POST" }),
  requestPasswordReset: (email) =>
    request("/auth/password-reset", { method: "POST", body: JSON.stringify({ email }) }),
  resetPassword: (token, password) =>
    request("/auth/password-reset/confirm", { method: "POST", body: JSON.stringify({ token, password }) }),
  deleteAccount: (password) => request("/auth/me", { method: "DELETE", body: JSON.stringify({ password }) }),
  requestEmailChange: (newEmail, password) =>
    request("/auth/email-change", { method: "POST", body: JSON.stringify({ new_email: newEmail, password }) }),
  confirmEmailChange: (token) =>
    request("/auth/email-change/confirm", { method: "POST", body: JSON.stringify({ token }) }),
  exportData: () => request("/auth/me/export"),
  getProfile: () => request("/profile"),
  updateProfile: (body) => request("/profile", { method: "PATCH", body: JSON.stringify(body) }),
  checkUsername: (username) => request(`/profile/username-check?${new URLSearchParams({ username })}`),
  setAvatar: (jpeg) => request("/profile/avatar", { method: "PUT", body: jpeg, headers: { "Content-Type": "image/jpeg" } }),
  removeAvatar: () => request("/profile/avatar", { method: "DELETE" }),
  getPerson: (username) => request(`/people/${encodeURIComponent(username)}`),
  getFollowCounts: () => request("/follows"),
  listFollowPage: (username, kind, cursor) =>
    request(`/people/${encodeURIComponent(username)}/${kind}${cursor ? `?${new URLSearchParams({ cursor })}` : ""}`),
  checkUsernameForSignup: (username) => request(`/auth/username-check?${new URLSearchParams({ username })}`),
  follow: (username) => request(`/follows/${encodeURIComponent(username)}`, { method: "PUT" }),
  unfollow: (username) => request(`/follows/${encodeURIComponent(username)}`, { method: "DELETE" }),
  removeFollower: (username) => request(`/followers/${encodeURIComponent(username)}`, { method: "DELETE" }),
  listBlocks: () => request("/blocks"),
  getLeaderboard: () => request("/leaderboard"),
  listConversations: () => request("/conversations"),
  countUnread: async () => (await request<{ unread: number }>("/conversations/unread")).unread,
  listReceived: (cursor) => request(`/inbox${cursor ? `?${new URLSearchParams({ cursor })}` : ""}`),
  countUnseenServes: async () => (await request<{ unseen: number }>("/inbox/unseen")).unseen,
  startConversation: (username) => request("/conversations", { method: "POST", body: JSON.stringify({ username }) }),
  getConversation: (id) => request(`/conversations/${encodeURIComponent(id)}`),
  listMessages: (id, before) =>
    request(`/conversations/${encodeURIComponent(id)}/messages${before ? `?${new URLSearchParams({ before })}` : ""}`),
  sendMessage: (id, message) =>
    request(`/conversations/${encodeURIComponent(id)}/messages`, { method: "POST", body: JSON.stringify(message) }),
  markRead: (id) => request(`/conversations/${encodeURIComponent(id)}/read`, { method: "POST" }),
  deleteMessage: (id) => request(`/messages/${encodeURIComponent(id)}`, { method: "DELETE" }),
  report: (body) => request("/reports", { method: "POST", body: JSON.stringify(body) }),
  createPost: (body) => request("/posts", { method: "POST", body: JSON.stringify(body) }),
  getPost: (id) => request(`/posts/${encodeURIComponent(id)}`),
  editPost: (id, body) => request(`/posts/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(body) }),
  deletePost: (id) => request(`/posts/${encodeURIComponent(id)}`, { method: "DELETE" }),
  listPostsBy: (username, cursor) =>
    request(`/people/${encodeURIComponent(username)}/posts${cursor ? `?${new URLSearchParams({ cursor })}` : ""}`),
  getFeed: (tab, cursor) => request(`/feed?${new URLSearchParams({ tab, ...(cursor ? { cursor } : {}) })}`),
  like: (postId) => request(`/posts/${encodeURIComponent(postId)}/like`, { method: "PUT" }),
  unlike: (postId) => request(`/posts/${encodeURIComponent(postId)}/like`, { method: "DELETE" }),
  listComments: (postId, cursor) =>
    request(`/posts/${encodeURIComponent(postId)}/comments${cursor ? `?${new URLSearchParams({ cursor })}` : ""}`),
  addComment: (postId, body) =>
    request(`/posts/${encodeURIComponent(postId)}/comments`, { method: "POST", body: JSON.stringify({ body }) }),
  deleteComment: (id) => request(`/comments/${encodeURIComponent(id)}`, { method: "DELETE" }),
  listNotifications: () => request("/notifications"),
  countNotifications: async () => (await request<{ unread: number }>("/notifications/unread")).unread,
  markNotificationsRead: () => request("/notifications/read", { method: "POST" }),
  block: (username) => request("/blocks", { method: "POST", body: JSON.stringify({ username }) }),
  unblock: (username) => request(`/blocks/${encodeURIComponent(username)}`, { method: "DELETE" }),
  changePassword: (currentPassword, newPassword) =>
    request("/auth/password-change", {
      method: "POST",
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    }),
  getReport: (id) => (isDemoId(id) ? Promise.resolve(null) : request(`/analyses/${encodeURIComponent(id)}/report`)),
  reportAnalysis: (id, body) =>
    request(`/analyses/${encodeURIComponent(id)}/report`, { method: "PUT", body: JSON.stringify(body) }),
  deleteAnalysis: (id) => request(`/analyses/${encodeURIComponent(id)}`, { method: "DELETE" }),
  createAnalysis: (body) => request("/analyses", { method: "POST", body: JSON.stringify(body) }),
  uploadVideo: putWithProgress,
  startAnalysis: (id) => request(`/analyses/${encodeURIComponent(id)}/start`, { method: "POST" }),
  retryAnalysis: (id) => request(`/analyses/${encodeURIComponent(id)}/retry`, { method: "POST" }),
  getAnalysis: (id) => (isDemoId(id) ? demo(id, "summary.json") : request(`/analyses/${encodeURIComponent(id)}`)),
  listAnalyses: (cursor, query) => {
    const params = new URLSearchParams(query);
    if (cursor) params.set("cursor", cursor);
    const qs = params.toString();
    return request(`/analyses${qs ? `?${qs}` : ""}`);
  },
  setNote: (id, note) =>
    request(`/analyses/${encodeURIComponent(id)}/note`, { method: "PUT", body: JSON.stringify({ note }) }),
  getResult: (id) => (isDemoId(id) ? demo(id, "result.json") : request(`/analyses/${encodeURIComponent(id)}/result`)),
  getFrames: (id) => (isDemoId(id) ? demo(id, "frames.json") : request(`/analyses/${encodeURIComponent(id)}/frames`)),
};
