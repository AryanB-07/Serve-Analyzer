import { useState } from "react";
import { Link, useNavigate } from "react-router";

import { useConnections } from "../../api/friends";
import { useStartConversation } from "../../api/messages";
import { api } from "../../api";
import type { AnalysisSummary } from "../../api/types";
import { Avatar } from "../../components/Avatar";
import { displayName, friendsErrorMessage } from "../friends/FriendsPage";
import { ServePicker } from "../messages/ServePicker";

/** Above a serve a friend sent you: whose it is, that it's read-only, and comparing with yours. */
export function SharedBanner({ summary }: { summary: AnalysisSummary }) {
  const navigate = useNavigate();
  const [picking, setPicking] = useState(false);
  const by = summary.shared_by!;
  return (
    <div className="space-y-3 rounded-xl border border-accent/40 bg-accent/5 p-4">
      <div className="flex flex-wrap items-center gap-3">
        <Avatar url={by.avatar_url} name={by.display_name ?? by.username} size="sm" />
        <p className="min-w-0 flex-1 text-sm">
          <span className="font-medium">Shared by {displayName(by)}</span>
          <span className="text-ink-muted"> · read-only. You can watch and compare it; only they can change it.</span>
        </p>
        <button type="button" onClick={() => setPicking((v) => !v)} aria-expanded={picking}
          className="rounded-lg border border-border px-3 py-1.5 text-sm font-semibold hover:bg-surface-2">
          Compare with one of my serves
        </button>
      </div>
      {picking && (
        <ServePicker
          title="Compare with which of your serves?"
          onCancel={() => setPicking(false)}
          onPick={(mine) => navigate(`/compare?a=${mine.id}&b=${summary.id}`)}
        />
      )}
    </div>
  );
}

/** On your own serve: send it to a friend, in your conversation with them. */
export function SendToFriend({ summary }: { summary: AnalysisSummary }) {
  const [open, setOpen] = useState(false);
  const [sentTo, setSentTo] = useState<{ name: string; conversation: string } | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const connections = useConnections();
  const start = useStartConversation();
  const friends = connections.data?.friends ?? [];

  async function send(username: string, name: string) {
    setError(null);
    setBusy(username);
    try {
      const conversation = await start.mutateAsync(username);
      await api.sendMessage(conversation.id, { analysis_id: summary.id });
      setSentTo({ name, conversation: conversation.id });
      setOpen(false);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="relative">
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open}
        className="rounded-lg border border-border px-3 py-1.5 text-sm font-medium hover:bg-surface-2">
        Send to a friend
      </button>
      {sentTo && (
        <p role="status" className="mt-1 text-sm">
          Sent to {sentTo.name}. <Link to={`/messages/${sentTo.conversation}`} className="text-accent underline">Open the conversation</Link>
        </p>
      )}
      {open && (
        <div className="absolute right-0 top-full z-30 mt-2 w-72 space-y-2 rounded-xl border border-border bg-surface p-3 shadow-xl">
          <p className="text-sm font-semibold">Send this serve to…</p>
          {friends.length === 0 ? (
            <p className="text-sm text-ink-muted">
              No friends yet. <Link to="/friends" className="text-accent underline">Find someone</Link>
            </p>
          ) : (
            <ul className="max-h-64 space-y-1 overflow-y-auto">
              {friends.map((f) => f.person.username && (
                <li key={f.id}>
                  <button type="button" disabled={busy !== null} onClick={() => send(f.person.username!, displayName(f.person))}
                    className="flex w-full items-center gap-2 rounded-lg p-1.5 text-left text-sm hover:bg-surface-2 disabled:opacity-50">
                    <Avatar url={f.person.avatar_url} name={f.person.display_name ?? f.person.username} size="sm" />
                    <span className="min-w-0 flex-1 truncate">{displayName(f.person)}</span>
                    {busy === f.person.username && <span className="text-xs text-ink-muted">Sending…</span>}
                  </button>
                </li>
              ))}
            </ul>
          )}
          <p className="text-xs text-ink-muted">They'll be able to watch it, without your note or filename, until you delete the message.</p>
          {error != null && <p role="alert" className="text-sm text-bad">{friendsErrorMessage(error)}</p>}
        </div>
      )}
    </div>
  );
}
