import { useState } from "react";
import { api, ApiError } from "../api/client";
import { useFetch } from "../api/hooks";
import { Menu } from "./Menu";
import type { TransferMode, TransferResult } from "../api/types";

interface TransferMenuProps {
  projectId: string;
  /** Resolved at the moment the user picks a target, not eagerly — lets
   * callers (e.g. a phase's "transfer" action) compute the task id set
   * lazily instead of keeping it in sync with every render. */
  resolveTaskIds: () => Promise<string[]>;
  onDone: (result: TransferResult, mode: TransferMode) => void;
  onError: (message: string) => void;
}

/** The "Copy to project…" / "Move to project…" pair, reused by the Tasks
 * bulk-action bar, a single task's editor, and a phase's transfer action.
 * Lists every other project plus a "New project…" entry that prompts for
 * a name, then calls the same POST /tasks/transfer endpoint either way. */
export function TransferMenu({ projectId, resolveTaskIds, onDone, onError }: TransferMenuProps) {
  const { data: projects } = useFetch(() => api.listProjects(), [projectId]);
  const [busy, setBusy] = useState(false);

  const others = (projects ?? []).filter((p) => p.id !== projectId);

  async function run(target: { targetProjectId: string } | { newProjectName: string }, mode: TransferMode) {
    setBusy(true);
    try {
      const taskIds = await resolveTaskIds();
      if (taskIds.length === 0) {
        onError("Nothing to transfer.");
        return;
      }
      const result = await api.transferTasks(projectId, taskIds, target, mode);
      onDone(result, mode);
    } catch (e) {
      onError(e instanceof ApiError ? e.detail : String(e));
    } finally {
      setBusy(false);
    }
  }

  function itemsFor(mode: TransferMode) {
    return [
      ...others.map((p) => ({ label: p.name, onSelect: () => run({ targetProjectId: p.id }, mode) })),
      {
        label: "＋ New project…",
        onSelect: () => {
          const name = window.prompt("New project name:");
          if (name?.trim()) run({ newProjectName: name.trim() }, mode);
        },
      },
    ];
  }

  return (
    <>
      <Menu label={busy ? "Working…" : "Copy to project"} items={itemsFor("copy")} />
      <Menu label={busy ? "Working…" : "Move to project"} items={itemsFor("move")} />
    </>
  );
}
