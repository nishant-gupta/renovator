import { useState } from "react";
import { api, ApiError } from "../api/client";
import { useFetch } from "../api/hooks";
import { Menu } from "../components/Menu";
import { TransferMenu } from "../components/TransferMenu";
import { money } from "../format";
import type { Setup, TaskView, TransferResult } from "../api/types";
import { TaskEditor } from "./TaskEditor";
import { TemplatePicker } from "./TemplatePicker";

export function TasksTab({ projectId, planVersion }: { projectId: string; planVersion: number }) {
  const { data: setup, error: setupError, loading: setupLoading } = useFetch(
    () => api.getSetup(projectId),
    [projectId, planVersion],
  );
  const { data: fetchedTasks, error: tasksError, loading: tasksLoading } = useFetch(
    () => api.getTasks(projectId),
    [projectId, planVersion],
  );

  // Local override so a create/update/delete's response renders immediately
  // without waiting on a refetch round-trip. Cleared on an externally
  // sourced change (chat, or another tab) so the fresh fetch — not this
  // possibly-stale override — wins. Adjusted during render (React's
  // recommended pattern for "reset state when a prop changes") rather
  // than in an effect, which would cost an extra render pass.
  const [tasks, setTasks] = useState<TaskView[] | null>(null);
  const [lastPlanVersion, setLastPlanVersion] = useState(planVersion);
  if (planVersion !== lastPlanVersion) {
    setLastPlanVersion(planVersion);
    setTasks(null);
  }
  const effectiveTasks = tasks ?? fetchedTasks;

  const [editingTask, setEditingTask] = useState<TaskView | "new" | null>(null);
  const [showTemplates, setShowTemplates] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkError, setBulkError] = useState<string | null>(null);
  const [bulkNote, setBulkNote] = useState<string | null>(null);

  function applyTasks(next: TaskView[]) {
    setTasks(next);
    setEditingTask(null);
    setShowTemplates(false);
  }

  function toggleSelect(taskId: string, checked: boolean) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (checked) next.add(taskId);
      else next.delete(taskId);
      return next;
    });
  }

  async function runBulk(action: () => Promise<TaskView[]>) {
    setBulkError(null);
    try {
      applyTasks(await action());
      setSelected(new Set());
    } catch (e) {
      if (e instanceof ApiError && e.needsConfirmation) {
        if (window.confirm(e.detail)) {
          try {
            applyTasks(await action());
            setSelected(new Set());
          } catch (e2) {
            setBulkError(e2 instanceof ApiError ? e2.detail : String(e2));
          }
        }
      } else {
        setBulkError(e instanceof ApiError ? e.detail : String(e));
      }
    }
  }

  async function handleTransferDone(result: TransferResult, mode: "copy" | "move") {
    setBulkError(null);
    setBulkNote(
      `${result.transferred_task_count} task${result.transferred_task_count === 1 ? "" : "s"} ${
        mode === "move" ? "moved" : "copied"
      } to project "${result.target_project_id}".`,
    );
    applyTasks(await api.getTasks(projectId));
    setSelected(new Set());
  }

  if (setupLoading || tasksLoading) return <div className="empty">Loading…</div>;
  if (setupError) return <div className="empty empty-error">Couldn't load setup: {setupError}</div>;
  if (tasksError) return <div className="empty empty-error">Couldn't load tasks: {tasksError}</div>;
  if (!setup || !effectiveTasks) return null;

  const total = effectiveTasks.reduce((s, t) => s + t.total_cost, 0);
  const noRooms = setup.rooms.length === 0;
  const visibleIds = effectiveTasks.map((t) => t.task_id);
  const allSelected = visibleIds.length > 0 && visibleIds.every((id) => selected.has(id));
  const ids = [...selected];

  return (
    <div>
      <h1 className="page-h">Tasks</h1>
      <p className="page-sub">
        {effectiveTasks.length} task{effectiveTasks.length === 1 ? "" : "s"} · {money(total)}. Click a row to edit.
      </p>

      {noRooms && <div className="banner banner-error">Add a room on the Setup tab before adding tasks.</div>}
      {bulkError && <div className="banner banner-error">{bulkError}</div>}
      {bulkNote && <div className="banner banner-info">{bulkNote}</div>}

      <div className="tab-toolbar">
        <button className="btn-ghost" disabled={noRooms} onClick={() => setShowTemplates(true)}>
          ✦ From template
        </button>
        <button className="btn" disabled={noRooms} onClick={() => setEditingTask("new")}>
          + Add task
        </button>
      </div>

      {ids.length > 0 && (
        <BulkBar
          projectId={projectId}
          count={ids.length}
          setup={setup}
          onMarkMandatory={(mandatory) => runBulk(() => api.bulkSetMandatory(projectId, ids, mandatory))}
          onMoveToPhase={(phaseId) => runBulk(() => api.bulkMoveToPhase(projectId, ids, phaseId))}
          onMoveToStage={(stageId) =>
            runBulk(async () => {
              await api.moveTasksToStage(projectId, ids, stageId);
              return api.getTasks(projectId);
            })
          }
          onDelete={() => runBulk(() => api.bulkDeleteTasks(projectId, ids))}
          onClear={() => setSelected(new Set())}
          resolveTransferIds={() => Promise.resolve(ids)}
          onTransferDone={handleTransferDone}
          onTransferError={setBulkError}
        />
      )}

      <table className="dt">
        <thead>
          <tr>
            <th className="col-checkbox">
              <input
                type="checkbox"
                checked={allSelected}
                onChange={(e) => setSelected(e.target.checked ? new Set(visibleIds) : new Set())}
              />
            </th>
            <th>Room</th>
            <th>Task</th>
            <th>Category</th>
            <th>Type</th>
            <th className="num">Days</th>
            <th className="num">Cost</th>
            <th>Flag</th>
          </tr>
        </thead>
        <tbody>
          {effectiveTasks.length === 0 && (
            <tr>
              <td colSpan={8} className="empty-cell">
                No tasks yet.
              </td>
            </tr>
          )}
          {effectiveTasks.map((task) => (
            <tr key={task.task_id} className={`clickable-row ${selected.has(task.task_id) ? "sel" : ""}`}>
              <td className="col-checkbox">
                <input
                  type="checkbox"
                  checked={selected.has(task.task_id)}
                  onChange={(e) => toggleSelect(task.task_id, e.target.checked)}
                  onClick={(e) => e.stopPropagation()}
                />
              </td>
              <td onClick={() => setEditingTask(task)}>{task.room}</td>
              <td onClick={() => setEditingTask(task)}>
                {task.name}
                {task.is_split && <span className="tag tag-muted"> Mat+Lab</span>}
              </td>
              <td className="muted" onClick={() => setEditingTask(task)}>
                {task.category}
              </td>
              <td onClick={() => setEditingTask(task)}>{task.is_split ? "Material + Labor" : task.lines[0]?.line_type}</td>
              <td className="num" onClick={() => setEditingTask(task)}>
                {task.duration_days ?? "—"}
              </td>
              <td className="num" onClick={() => setEditingTask(task)}>
                {money(task.total_cost)}
              </td>
              <td onClick={() => setEditingTask(task)}>
                <span className={`tag ${task.mandatory ? "tag-mandatory" : "tag-optional"}`}>
                  {task.mandatory ? "Mandatory" : "Optional"}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {editingTask && (
        <TaskEditor
          projectId={projectId}
          setup={setup}
          task={editingTask === "new" ? null : editingTask}
          onClose={() => setEditingTask(null)}
          onSaved={applyTasks}
        />
      )}

      {showTemplates && (
        <TemplatePicker
          projectId={projectId}
          setup={setup}
          onClose={() => setShowTemplates(false)}
          onStartBlank={() => {
            setShowTemplates(false);
            setEditingTask("new");
          }}
          onCreated={applyTasks}
        />
      )}
    </div>
  );
}

function BulkBar({
  projectId,
  count,
  setup,
  onMarkMandatory,
  onMoveToPhase,
  onMoveToStage,
  onDelete,
  onClear,
  resolveTransferIds,
  onTransferDone,
  onTransferError,
}: {
  projectId: string;
  count: number;
  setup: Setup;
  onMarkMandatory: (mandatory: boolean) => void;
  onMoveToPhase: (phaseId: number) => void;
  onMoveToStage: (stageId: number | null) => void;
  onDelete: () => void;
  onClear: () => void;
  resolveTransferIds: () => Promise<string[]>;
  onTransferDone: (result: TransferResult, mode: "copy" | "move") => void;
  onTransferError: (message: string) => void;
}) {
  return (
    <div className="bulk-bar">
      <div className="bulk-bar-left">
        <span className="bulk-count-badge">{count}</span>
        <span>selected</span>
        <button type="button" className="bulk-clear" onClick={onClear}>
          Clear
        </button>
      </div>
      <div className="bulk-bar-actions">
        <div className="seg">
          <button type="button" onClick={() => onMarkMandatory(true)}>
            Mandatory
          </button>
          <button type="button" onClick={() => onMarkMandatory(false)}>
            Optional
          </button>
        </div>
        <Menu
          label="Move to phase"
          items={setup.phases.map((p) => ({ label: p.label, onSelect: () => onMoveToPhase(p.id) }))}
        />
        <Menu
          label="Move to stage"
          items={setup.stages.map((s) => ({ label: s.label, onSelect: () => onMoveToStage(s.id) }))}
        />
        <div className="bulk-divider" />
        <TransferMenu
          projectId={projectId}
          resolveTaskIds={resolveTransferIds}
          onDone={onTransferDone}
          onError={onTransferError}
        />
        <div className="bulk-divider" />
        <button type="button" className="btn-danger" onClick={onDelete}>
          Delete
        </button>
      </div>
    </div>
  );
}
