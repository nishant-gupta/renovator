import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import { toolLabel } from "../toolLabels";
import { Markdown } from "./Markdown";
import type { ChatEvent, ChatInterruptAction, ChatResumeDecision } from "../api/types";

interface ChatPanelProps {
  projectId: string;
  hasLlmKey: boolean;
}

// A room photo attached to a live send is shown for real (we still have
// the data URL client-side); one recovered via history replay only ever
// carries `hasImage` (the backend never echoes image bytes back out), so
// it renders as a placeholder instead.
type HistoryItem =
  | { id: number; kind: "user"; content: string; imageUrl?: string; hasImage?: boolean }
  | { id: number; kind: "tool_result"; name: string; content: string }
  | { id: number; kind: "assistant"; content: string }
  | { id: number; kind: "interrupt"; actions: ChatInterruptAction[]; status: "pending" | "approved" | "rejected" }
  | { id: number; kind: "error"; message: string };

const MAX_IMAGE_BYTES = 8 * 1024 * 1024;

/** The chat bubble only ever shows one short line per tool call — "Checked
 * schedule", "Updated a rate failed: ..." — never the raw args/JSON
 * result. The full call (name + args) and result (name + content) are
 * still `console.debug`'d as they happen, so a developer can inspect them
 * in devtools without the transcript itself being noisy. There's no
 * LangSmith/tracing wired up yet (a Phase 9 item) — this is the interim
 * "look at the logs" story. */
function summarizeToolResult(name: string, content: string): { failed: boolean; text: string } {
  let parsed: unknown;
  try {
    parsed = JSON.parse(content);
  } catch {
    parsed = null;
  }
  if (parsed && typeof parsed === "object" && "error" in (parsed as Record<string, unknown>)) {
    return { failed: true, text: `${toolLabel(name)} — ${String((parsed as Record<string, unknown>).error)}` };
  }
  return { failed: false, text: toolLabel(name) };
}

// A plain `Omit<HistoryItem, "id">` collapses the union into one merged
// shape; this conditional distributes over it so each variant keeps its
// own fields minus `id`.
type NewHistoryItem = HistoryItem extends infer T ? (T extends { id: number } ? Omit<T, "id"> : never) : never;

/** The chat dock (design doc §4.10, Phase 7) — a plain, additional way to
 * call the same tool layer the tabs call directly; it never mutates the
 * Plan through its own path. On mount, it replays `GET .../chat/history`
 * (the LangGraph checkpointer's record for this project's thread) so a
 * page reload recovers the transcript — and, if the thread was left
 * mid-interrupt, the pending approve/reject prompt too, without needing
 * any extra recovery UI: it's just the last replayed event. */
export function ChatPanel({ projectId, hasLlmKey }: ChatPanelProps) {
  const [open, setOpen] = useState(false);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [pendingImage, setPendingImage] = useState<string | null>(null);
  const [imageError, setImageError] = useState<string | null>(null);
  const nextId = useRef(0);
  const scrollRef = useRef<HTMLDivElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  function push(item: NewHistoryItem) {
    const withId = { ...item, id: nextId.current++ } as HistoryItem;
    setHistory((prev) => [...prev, withId]);
    queueMicrotask(() => scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight }));
  }

  // `stream_turn` always echoes the user's own message back as the first
  // event of a turn — necessary so a page reload can replay it from
  // /chat/history, but redundant right after send() already rendered it
  // optimistically. `skipUserEcho` drops just that one duplicate; history
  // replay (on mount) needs the echo, so it doesn't set this.
  function handleEvent(event: ChatEvent, options: { skipUserEcho?: boolean } = {}) {
    switch (event.type) {
      case "tool_call":
        // Not shown in the transcript — see summarizeToolResult's comment.
        event.calls.forEach((c) => console.debug(`[chat] → ${c.name}`, c.args));
        break;
      case "tool_result":
        console.debug(`[chat] ✓ ${event.name}`, event.content);
        push({ kind: "tool_result", name: event.name, content: event.content });
        break;
      case "message":
        if (event.role === "user") {
          if (!options.skipUserEcho) push({ kind: "user", content: event.content, hasImage: event.has_image });
        } else {
          push({ kind: "assistant", content: event.content });
        }
        break;
      case "interrupt":
        push({ kind: "interrupt", actions: event.actions, status: "pending" });
        break;
      case "error":
        push({ kind: "error", message: event.message });
        break;
      case "done":
        break;
    }
  }

  useEffect(() => {
    if (!hasLlmKey) return;
    api
      .getChatHistory(projectId)
      .then((res) => res.events.forEach((e) => handleEvent(e)))
      .catch((e) => setLoadError(e instanceof ApiError ? e.detail : String(e)));
    // Runs once per mount — this component is keyed by projectId in
    // App.tsx, so a project switch remounts it fresh rather than needing
    // this effect to react to a changing id.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // The collapsed state (`!open`) doesn't render `.chat-history` at all, so
  // reopening remounts it at scroll position 0 — jump back to the bottom
  // once it's back in the DOM. `requestAnimationFrame` waits for that
  // render/layout pass; a plain effect body would run too early.
  useEffect(() => {
    if (!open) return;
    const frame = requestAnimationFrame(() => {
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
    });
    return () => cancelAnimationFrame(frame);
  }, [open]);

  function attachPhoto(file: File) {
    setImageError(null);
    if (file.size > MAX_IMAGE_BYTES) {
      setImageError("That photo is too large (max 8MB).");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => setPendingImage(reader.result as string);
    reader.onerror = () => setImageError("Couldn't read that file.");
    reader.readAsDataURL(file);
  }

  async function send() {
    const message = input.trim();
    const image = pendingImage;
    if ((!message && !image) || busy) return;
    setInput("");
    setPendingImage(null);
    push({ kind: "user", content: message, imageUrl: image ?? undefined });
    setBusy(true);
    try {
      await api.streamChat(projectId, image ? { message, image } : { message }, (e) =>
        handleEvent(e, { skipUserEcho: true }),
      );
    } catch (e) {
      push({ kind: "error", message: e instanceof ApiError ? e.detail : String(e) });
    } finally {
      setBusy(false);
    }
  }

  async function resolveInterrupt(item: HistoryItem & { kind: "interrupt" }, approve: boolean) {
    setHistory((prev) =>
      prev.map((it) => (it.id === item.id ? { ...it, status: approve ? "approved" : "rejected" } : it)),
    );
    const decisions: ChatResumeDecision[] = item.actions.map(() =>
      approve ? { type: "approve" } : { type: "reject", message: "User declined." },
    );
    setBusy(true);
    try {
      await api.streamChat(projectId, { resume: { decisions } }, handleEvent);
    } catch (e) {
      push({ kind: "error", message: e instanceof ApiError ? e.detail : String(e) });
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button className="chat-fab" onClick={() => setOpen(true)} title="Open agent chat">
        💬
      </button>
    );
  }

  return (
    <aside className="chat-dock">
      <div className="chat-header">
        <span>Agent chat</span>
        <button className="icon-btn" title="Collapse" onClick={() => setOpen(false)}>
          ✕
        </button>
      </div>

      {!hasLlmKey ? (
        <div className="chat-empty">
          No ANTHROPIC_API_KEY configured on the backend — chat is disabled. Every tab still works fully
          without it.
        </div>
      ) : (
        <>
          {loadError && <div className="banner banner-error">Couldn't load chat history: {loadError}</div>}
          <div className="chat-history" ref={scrollRef}>
            {history.length === 0 && (
              <div className="chat-empty">Ask the agent to add tasks, reschedule, or explain the plan.</div>
            )}
            {history.map((item) => {
              if (item.kind === "user") {
                return (
                  <div key={item.id} className="chat-bubble chat-bubble-user">
                    {item.imageUrl && <img className="chat-photo" src={item.imageUrl} alt="Attached room photo" />}
                    {!item.imageUrl && item.hasImage && <div className="chat-photo-placeholder">📷 photo</div>}
                    {item.content}
                  </div>
                );
              }
              if (item.kind === "assistant") {
                return (
                  <div key={item.id} className="chat-bubble chat-bubble-assistant chat-markdown">
                    <Markdown text={item.content} />
                  </div>
                );
              }
              if (item.kind === "tool_result") {
                const { failed, text } = summarizeToolResult(item.name, item.content);
                return (
                  <div key={item.id} className={`chat-tool-line chat-tool-line-result ${failed ? "chat-tool-line-failed" : ""}`}>
                    {failed ? "⚠" : "✓"} {text}
                  </div>
                );
              }
              if (item.kind === "error") {
                return (
                  <div key={item.id} className="banner banner-error">
                    {item.message}
                  </div>
                );
              }
              // interrupt
              return (
                <div key={item.id} className="chat-interrupt">
                  {item.actions.map((a, i) => (
                    <div key={i}>
                      <strong>{toolLabel(a.name)}</strong>
                      <div className="chat-tool-line">{JSON.stringify(a.args)}</div>
                    </div>
                  ))}
                  {item.status === "pending" ? (
                    <div className="row-actions">
                      <button className="btn-ghost" onClick={() => resolveInterrupt(item, false)}>
                        Reject
                      </button>
                      <button className="btn" onClick={() => resolveInterrupt(item, true)}>
                        Approve
                      </button>
                    </div>
                  ) : (
                    <span className={`tag ${item.status === "approved" ? "tag-active" : "tag-mandatory"}`}>
                      {item.status === "approved" ? "Approved" : "Rejected"}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
          {imageError && <div className="banner banner-error">{imageError}</div>}
          {pendingImage && (
            <div className="chat-photo-pending">
              <img src={pendingImage} alt="Room photo to send" />
              <button className="icon-btn" title="Remove photo" onClick={() => setPendingImage(null)}>
                ✕
              </button>
            </div>
          )}
          <div className="chat-input-row">
            <button
              className="icon-btn"
              title="Attach a room photo"
              disabled={busy}
              onClick={() => fileInput.current?.click()}
            >
              📷
            </button>
            <input
              ref={fileInput}
              type="file"
              accept="image/*"
              style={{ display: "none" }}
              onChange={(e) => {
                const file = e.target.files?.[0];
                e.target.value = "";
                if (file) attachPhoto(file);
              }}
            />
            <input
              type="text"
              value={input}
              placeholder="Ask the agent…"
              disabled={busy}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") send();
              }}
            />
            <button className="btn" disabled={busy || (!input.trim() && !pendingImage)} onClick={send}>
              {busy ? "…" : "Send"}
            </button>
          </div>
        </>
      )}
    </aside>
  );
}
