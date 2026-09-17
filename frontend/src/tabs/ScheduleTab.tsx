import { useState } from "react";
import { api } from "../api/client";
import { useFetch } from "../api/hooks";
import { fmtDate } from "../format";
import { tradeBucket, tradeColorVar } from "../trade";
import type { TaskView } from "../api/types";
import { TaskEditor } from "./TaskEditor";
import { GanttView } from "./GanttView";
import { AgendaView } from "./AgendaView";
import { BoardView } from "./BoardView";

type View = "timeline" | "agenda" | "board";

export function ScheduleTab({ projectId, planVersion }: { projectId: string; planVersion: number }) {
  const { data: setup, error: setupError, loading: setupLoading, reload: reloadSetup } = useFetch(
    () => api.getSetup(projectId),
    [projectId, planVersion],
  );
  const { data: schedule, error: scheduleError, loading: scheduleLoading, reload: reloadSchedule } = useFetch(
    () => api.getSchedule(projectId),
    [projectId, planVersion],
  );

  const [view, setView] = useState<View>("timeline");
  const [editing, setEditing] = useState<{ task: TaskView | null; presetStageId?: number | null } | null>(null);

  function reloadAll() {
    reloadSetup();
    reloadSchedule();
  }

  async function openTask(taskId: string) {
    const tasks = await api.getTasks(projectId);
    const task = tasks.find((t) => t.task_id === taskId);
    if (task) setEditing({ task });
  }

  async function reorderStages(fromIndex: number, toIndex: number) {
    if (fromIndex === toIndex) return;
    const direction = fromIndex < toIndex ? 1 : -1;
    let idx = fromIndex;
    while (idx !== toIndex) {
      await api.moveStage(projectId, idx, direction);
      idx += direction;
    }
    reloadAll();
  }

  if (setupLoading || scheduleLoading) return <div className="empty">Loading…</div>;
  if (setupError) return <div className="empty empty-error">Couldn't load setup: {setupError}</div>;
  if (scheduleError) return <div className="empty empty-error">Couldn't load schedule: {scheduleError}</div>;
  if (!setup || !schedule) return null;

  const tradeKeys = [...new Set(schedule.tasks.map((t) => tradeBucket(t.worker_type || t.category).key))];
  const tradeNames = new Map(
    schedule.tasks.map((t) => {
      const b = tradeBucket(t.worker_type || t.category);
      return [b.key, b.name] as const;
    }),
  );

  return (
    <div>
      <h1 className="page-h">Schedule</h1>
      <p className="page-sub">
        Dates come from each task's duration, its dependencies, and the stage order — starting from the project date
        in Setup.
      </p>

      <div className="row between schedule-header-row">
        <div className="seg">
          <button className={view === "timeline" ? "active" : ""} onClick={() => setView("timeline")}>
            Timeline
          </button>
          <button className={view === "agenda" ? "active" : ""} onClick={() => setView("agenda")}>
            By date
          </button>
          <button className={view === "board" ? "active" : ""} onClick={() => setView("board")}>
            Board
          </button>
        </div>
        <div className="muted">
          Project runs <b>{fmtDate(schedule.project_start)}</b> → <b>{fmtDate(schedule.project_end)}</b>
        </div>
      </div>

      <div className="schedule-toggles schedule-toggles-spaced">
        <label>
          <input
            type="checkbox"
            checked={setup.sequence_stages}
            onChange={(e) => api.updateSettings(projectId, { sequence_stages: e.target.checked }).then(reloadAll)}
          />
          Run stages in order
        </label>
        <label>
          <input
            type="checkbox"
            checked={setup.work_weekends}
            onChange={(e) => api.updateSettings(projectId, { work_weekends: e.target.checked }).then(reloadAll)}
          />
          Work weekends
        </label>
      </div>

      <div className="legend">
        {tradeKeys.map((key) => (
          <span className="legend-item" key={key}>
            <span className="dot" style={{ background: tradeColorVar(key) }} />
            {tradeNames.get(key)}
          </span>
        ))}
      </div>

      {view === "timeline" && (
        <GanttView tasks={schedule.tasks} stages={setup.stages} onOpenTask={openTask} />
      )}
      {view === "agenda" && (
        <AgendaView tasks={schedule.tasks} workWeekends={setup.work_weekends} onOpenTask={openTask} />
      )}
      {view === "board" && (
        <BoardView
          projectId={projectId}
          tasks={schedule.tasks}
          stages={setup.stages}
          onOpenTask={openTask}
          onAddToStage={(stageId) => setEditing({ task: null, presetStageId: stageId })}
          onChanged={reloadAll}
          onReorderStages={reorderStages}
        />
      )}

      {editing && (
        <TaskEditor
          projectId={projectId}
          setup={setup}
          task={editing.task}
          presetStageId={editing.presetStageId}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            reloadAll();
          }}
        />
      )}
    </div>
  );
}
