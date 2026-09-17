import { useState } from "react";
import { api, ApiError } from "../api/client";
import { useFetch } from "../api/hooks";
import { StatRow, Stat } from "../components/Stat";
import { money } from "../format";
import type { TaskStatus, TaskView } from "../api/types";

const STATUSES: TaskStatus[] = ["Not Started", "In Progress", "On Hold", "Done"];

// Mirrors read_tools.get_track_summary's combined_status rule exactly
// (backend/src/renovator/tools/read_tools.py) so a split task's header row
// shows the same status the backend would compute.
function combineLineStatuses(statuses: TaskStatus[]): TaskStatus {
  const set = new Set(statuses);
  if (set.size === 1 && set.has("Done")) return "Done";
  if (set.has("In Progress")) return "In Progress";
  if (set.size === 1 && set.has("On Hold")) return "On Hold";
  return "Not Started";
}

export function TrackTab({ projectId, planVersion }: { projectId: string; planVersion: number }) {
  const { data: track, error: trackError, loading: trackLoading } = useFetch(
    () => api.getTrack(projectId),
    [projectId, planVersion],
  );
  const { data: tasks, error: tasksError, loading: tasksLoading, reload } = useFetch(
    () => api.getTasks(projectId),
    [projectId, planVersion],
  );
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  async function setLine(lineId: string, patch: { status?: TaskStatus; actual_cost?: number }) {
    try {
      await api.updateLine(projectId, lineId, patch);
      reload();
    } catch (e) {
      window.alert(e instanceof ApiError ? e.detail : String(e));
    }
  }

  function toggleExpand(taskId: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(taskId)) next.delete(taskId);
      else next.add(taskId);
      return next;
    });
  }

  if (trackLoading || tasksLoading) return <div className="empty">Loading…</div>;
  if (trackError) return <div className="empty empty-error">Couldn't load track: {trackError}</div>;
  if (tasksError) return <div className="empty empty-error">Couldn't load tasks: {tasksError}</div>;
  if (!track || !tasks) return null;

  const overBudget = track.variance != null && track.variance > 0;

  return (
    <div>
      <h1 className="page-h">Track</h1>
      <p className="page-sub">
        Log status and what you actually spent against the estimate. Split tasks show a combined figure — expand to
        log material and labour separately.
      </p>

      <StatRow>
        <Stat label="Progress" value={`${track.progress_pct}%`} note={`${track.lines_done} / ${track.lines_total} lines done`} />
        <Stat label="Estimated" value={money(track.estimated_total)} />
        <Stat label="Actual so far" value={money(track.actual_total)} note={`${track.actuals_logged} logged`} />
        <Stat
          label="Variance"
          value={track.variance != null ? money(track.variance) : "—"}
          tone={overBudget ? "danger" : "ok"}
        />
      </StatRow>

      <table className="dt">
        <thead>
          <tr>
            <th></th>
            <th>Room</th>
            <th>Task</th>
            <th className="num">Est.</th>
            <th className="num">Actual</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {tasks.length === 0 && (
            <tr>
              <td colSpan={6} className="empty-cell">
                No tasks match.
              </td>
            </tr>
          )}
          {tasks.map((task) => (
            <TaskRows
              key={task.task_id}
              task={task}
              expanded={expanded.has(task.task_id)}
              onToggle={() => toggleExpand(task.task_id)}
              onEditLine={setLine}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TaskRows({
  task,
  expanded,
  onToggle,
  onEditLine,
}: {
  task: TaskView;
  expanded: boolean;
  onToggle: () => void;
  onEditLine: (lineId: string, patch: { status?: TaskStatus; actual_cost?: number }) => void;
}) {
  if (!task.is_split) {
    const line = task.lines[0];
    return (
      <tr>
        <td></td>
        <td>{task.room}</td>
        <td>{task.name}</td>
        <td className="num">{money(task.total_cost)}</td>
        <td className="num">
          <input
            type="number"
            placeholder="—"
            defaultValue={line?.actual_cost ?? ""}
            className="num-input-sm"
            onBlur={(e) => {
              const value = e.target.value === "" ? undefined : Number(e.target.value);
              if (line && value !== undefined && value !== line.actual_cost) onEditLine(line.line_id, { actual_cost: value });
            }}
          />
        </td>
        <td>
          <select
            className="status-select"
            value={line?.status}
            onChange={(e) => line && onEditLine(line.line_id, { status: e.target.value as TaskStatus })}
          >
            {STATUSES.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </td>
      </tr>
    );
  }

  const anyActual = task.lines.some((l) => l.actual_cost != null);
  const totalActual = task.lines.reduce((s, l) => s + (l.actual_cost ?? 0), 0);
  const combinedStatus = combineLineStatuses(task.lines.map((l) => l.status));

  return (
    <>
      <tr className="clickable-row" onClick={onToggle}>
        <td>
          <button className="icon-btn" onClick={(e) => e.stopPropagation()}>
            {expanded ? "▾" : "▸"}
          </button>
        </td>
        <td>{task.room}</td>
        <td>
          {task.name} <span className="tag tag-muted">Mat+Lab</span>
        </td>
        <td className="num">{money(task.total_cost)}</td>
        <td className="num">{anyActual ? money(totalActual) : "—"}</td>
        <td>
          <span className="tag tag-muted">{combinedStatus}</span>
        </td>
      </tr>
      {expanded &&
        task.lines.map((line) => (
          <tr key={line.line_id} className="dt-subrow">
            <td></td>
            <td></td>
            <td className="muted">{line.line_type}</td>
            <td></td>
            <td className="num">
              <input
                type="number"
                placeholder="—"
                defaultValue={line.actual_cost ?? ""}
                className="num-input-sm"
                onBlur={(e) => {
                  const value = e.target.value === "" ? undefined : Number(e.target.value);
                  if (value !== undefined && value !== line.actual_cost) onEditLine(line.line_id, { actual_cost: value });
                }}
              />
            </td>
            <td>
              <select
                className="status-select"
                value={line.status}
                onChange={(e) => onEditLine(line.line_id, { status: e.target.value as TaskStatus })}
              >
                {STATUSES.map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            </td>
          </tr>
        ))}
    </>
  );
}
