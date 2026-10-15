import { useEffect, useId, useLayoutEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { Link, useParams } from "react-router";

import { ApiError } from "../../api/client";
import { useConversation, useDeleteMessage, useMarkRead, useMessages, useSendMessage } from "../../api/messages";
import type { ConversationSummary, Message } from "../../api/types";
import { Avatar } from "../../components/Avatar";
import { displayName, friendsErrorMessage } from "../friends/FriendsPage";
import { ReportForm } from "./ReportForm";

const MAX = 2000;

function when(iso: string) {
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function Bubble({ message, conversationId, other, seen }: {
  message: Message;
  conversationId: string;
  other: ConversationSummary["person"];
  seen: boolean;
}) {
  const remove = useDeleteMessage(conversationId);
  const [confirming, setConfirming] = useState(false);
  const [reporting, setReporting] = useState(false);
  const mine = message.from_you;
  const name = other ? displayName(other) : "Deleted account";
  return (
    <li className={`flex flex-col gap-1 ${mine ? "items-end" : "items-start"}`}>
      <div
        className={`max-w-[85%] whitespace-pre-wrap break-words rounded-2xl px-3.5 py-2 text-sm sm:max-w-[70%] ${
          message.deleted ? "border border-dashed border-border italic text-ink-muted"
            : mine ? "bg-accent text-on-accent" : "border border-border bg-surface"}`}
      >
        <span className="sr-only">{mine ? "You" : name}: </span>
        {message.deleted ? "Message deleted" : message.body}
      </div>
      <div className="flex items-center gap-3 px-1 text-xs text-ink-muted">
        <time dateTime={message.created_at}>{when(message.created_at)}</time>
        {mine && seen && <span>Seen</span>}
        {mine && !message.deleted && !confirming && (
          <button type="button" onClick={() => setConfirming(true)} className="hover:text-ink">Delete</button>
        )}
        {mine && confirming && (
          <>
            <span>Delete for everyone?</span>
            <button type="button" disabled={remove.isPending} onClick={() => remove.mutate(message.id)} className="font-semibold text-bad hover:underline">
              Yes, delete it
            </button>
            <button type="button" onClick={() => setConfirming(false)} className="hover:text-ink">Keep</button>
          </>
        )}
        {!mine && !message.deleted && other?.username && !reporting && (
          <button type="button" onClick={() => setReporting(true)} className="hover:text-ink">Report</button>
        )}
      </div>
      {remove.error && <p role="alert" className="text-xs text-bad">{friendsErrorMessage(remove.error)}</p>}
      {reporting && other?.username && (
        <div className="w-full max-w-md">
          <ReportForm username={other.username} name={name} messageId={message.id} onDone={() => setReporting(false)} />
        </div>
      )}
    </li>
  );
}

function Composer({ conversation }: { conversation: ConversationSummary }) {
  const id = useId();
  const send = useSendMessage(conversation.id);
  const [text, setText] = useState("");
  const tooLong = text.trim().length > MAX;

  function submit(event?: FormEvent) {
    event?.preventDefault();
    const body = text.trim();
    if (!body || tooLong || send.isPending) return;
    send.mutate(body, { onSuccess: () => setText("") });
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  }

  if (!conversation.can_send) {
    return (
      <p role="status" className="rounded-xl border border-border bg-surface p-3 text-center text-sm text-ink-muted">
        {conversation.why_not ?? "You can't send messages here."} You can still read the conversation.
      </p>
    );
  }
  return (
    <form onSubmit={submit} aria-label="Send a message" className="space-y-1">
      <div className="flex items-end gap-2">
        <label htmlFor={`${id}-text`} className="sr-only">Message</label>
        <textarea
          id={`${id}-text`}
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            send.reset();
          }}
          onKeyDown={onKeyDown}
          rows={Math.min(5, Math.max(1, text.split("\n").length))}
          placeholder="Write a message"
          aria-describedby={`${id}-hint`}
          className="min-h-11 w-full resize-none rounded-2xl border border-border bg-bg px-4 py-2.5 text-ink placeholder:text-ink-muted focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/40"
        />
        <button type="submit" disabled={!text.trim() || tooLong || send.isPending}
          className="h-11 shrink-0 rounded-full bg-accent px-5 text-sm font-semibold text-on-accent hover:bg-accent-strong disabled:opacity-50">
          {send.isPending ? "Sending…" : "Send"}
        </button>
      </div>
      <p id={`${id}-hint`} className="px-2 text-xs text-ink-muted">
        Enter sends; Shift+Enter starts a new line.
        {text.length > MAX - 200 && <span className={tooLong ? "text-bad" : ""}> {text.trim().length}/{MAX}</span>}
      </p>
      {send.error && <p role="alert" className="px-2 text-sm text-bad">{friendsErrorMessage(send.error)}</p>}
    </form>
  );
}

export function ConversationPage() {
  const { id = "" } = useParams();
  const conversation = useConversation(id);
  const messages = useMessages(id);
  const markRead = useMarkRead(id);
  const list = useRef<HTMLDivElement>(null);
  const [reporting, setReporting] = useState(false);
  const [blocked, setBlocked] = useState(false);

  const pages = messages.data?.pages ?? [];
  const items = pages.flatMap((p) => p.items).slice().reverse(); // oldest first
  const newest = items[items.length - 1];
  const seenUpTo = pages[0]?.seen_up_to ?? null;
  const lastMine = [...items].reverse().find((m) => m.from_you);

  // Read whatever arrives while the conversation is open.
  const newestTheirs = [...items].reverse().find((m) => !m.from_you)?.id;
  const mark = markRead.mutate;
  useEffect(() => {
    if (newestTheirs) mark();
  }, [newestTheirs, mark]);

  // Keep the newest message in view as messages arrive (but not when loading older ones).
  const newestId = newest?.id;
  useLayoutEffect(() => {
    const el = list.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [newestId]);

  const c = conversation.data;
  if (blocked) {
    return (
      <div role="status" className="mx-auto max-w-lg space-y-3 py-10 text-center">
        <h1 className="text-2xl font-semibold">Reported and blocked</h1>
        <p className="text-ink-muted">Thanks for telling us. They can't find you or message you, and haven't been told.</p>
        <Link to="/messages" className="font-medium text-accent hover:underline">Back to Messages</Link>
      </div>
    );
  }
  if (conversation.isError || messages.isError) {
    const missing = [conversation.error, messages.error].some((e) => e instanceof ApiError && e.status === 404);
    return (
      <div className="mx-auto max-w-lg space-y-3 py-10 text-center">
        <h1 className="text-2xl font-semibold">{missing ? "Conversation not found" : "We couldn't load this conversation"}</h1>
        <Link to="/messages" className="font-medium text-accent hover:underline">Back to Messages</Link>
      </div>
    );
  }
  if (!c || !messages.data) return <p className="text-ink-muted">Loading…</p>;

  const name = c.person ? displayName(c.person) : "Deleted account";
  return (
    <div className="mx-auto flex h-[calc(100dvh-10rem)] min-h-96 w-full max-w-2xl flex-col gap-3">
      <header className="flex items-center gap-3 border-b border-border pb-3">
        <Link to="/messages" className="text-sm text-ink-muted hover:text-ink" aria-label="Back to Messages">←</Link>
        <Avatar url={c.person?.avatar_url} name={c.person?.display_name ?? c.person?.username} size="sm" />
        <h1 className="min-w-0 flex-1 truncate text-lg font-semibold">
          {c.person?.username ? <Link to={`/u/${c.person.username}`} className="hover:underline">{name}</Link> : name}
        </h1>
        {c.person?.username && !reporting && (
          <button type="button" onClick={() => setReporting(true)} className="text-sm text-ink-muted hover:text-bad">Report…</button>
        )}
      </header>
      {reporting && c.person?.username && (
        <ReportForm username={c.person.username} name={name} onDone={() => setReporting(false)} onBlocked={() => setBlocked(true)} />
      )}
      <div ref={list} className="min-h-0 flex-1 overflow-y-auto pr-1" tabIndex={0} aria-label={`Messages with ${name}`} role="region">
        {messages.hasNextPage && (
          <div className="pb-3 text-center">
            <button type="button" onClick={() => messages.fetchNextPage()} disabled={messages.isFetchingNextPage}
              className="rounded-lg border border-border px-3 py-1.5 text-sm hover:bg-surface-2 disabled:opacity-50">
              {messages.isFetchingNextPage ? "Loading…" : "Load older messages"}
            </button>
          </div>
        )}
        {items.length === 0 ? (
          <p className="py-10 text-center text-sm text-ink-muted">No messages yet. Say hello.</p>
        ) : (
          <ol className="space-y-3" aria-live="polite" aria-relevant="additions">
            {items.map((m) => (
              <Bubble key={m.id} message={m} conversationId={c.id} other={c.person}
                seen={m.id === lastMine?.id && seenUpTo != null && seenUpTo >= m.created_at} />
            ))}
          </ol>
        )}
      </div>
      <Composer conversation={c} />
    </div>
  );
}
