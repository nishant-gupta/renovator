import { useState } from "react";
import { api, ApiError } from "../api/client";
import { useFetch } from "../api/hooks";
import { Menu } from "../components/Menu";
import { withConfirmRetry } from "../confirm";
import type { Setup, TransferMode, TransferResult } from "../api/types";

export function SetupTab({ projectId, planVersion }: { projectId: string; planVersion: number }) {
  const { data: setup, error, loading, reload } = useFetch(
    () => api.getSetup(projectId),
    [projectId, planVersion],
  );
  const [busyError, setBusyError] = useState<string | null>(null);
  const [transferNote, setTransferNote] = useState<string | null>(null);

  async function run(action: () => Promise<Setup>) {
    setBusyError(null);
    try {
      await action();
      reload();
    } catch (e) {
      setBusyError(e instanceof ApiError ? e.detail : String(e));
    }
  }

  if (loading) return <div className="empty">Loading…</div>;
  if (error) return <div className="empty empty-error">Couldn't load setup: {error}</div>;
  if (!setup) return null;

  return (
    <div>
      <h1 className="page-h">Setup</h1>
      <p className="page-sub">
        The building blocks every other tab reuses — rooms, phases, and stage order. Project timing and the rate
        card have moved to that project's settings, on the Projects tab.
      </p>
      {busyError && <div className="banner banner-error">{busyError}</div>}
      {transferNote && <div className="banner banner-info">{transferNote}</div>}

      <div className="card-grid">
        <RoomsCard projectId={projectId} setup={setup} run={run} />
        <PhasesCard
          projectId={projectId}
          setup={setup}
          run={run}
          onTransferDone={(result, mode) => {
            setTransferNote(
              `${result.transferred_task_count} task${result.transferred_task_count === 1 ? "" : "s"} ${
                mode === "move" ? "moved" : "copied"
              } to project "${result.target_project_id}".`,
            );
            setBusyError(null);
          }}
          onTransferError={(message) => {
            setBusyError(message);
            setTransferNote(null);
          }}
        />
      </div>

      <StagesCard projectId={projectId} setup={setup} run={run} />
    </div>
  );
}

interface CardProps {
  projectId: string;
  setup: Setup;
  run: (action: () => Promise<Setup>) => Promise<void>;
}

function RoomsCard({ projectId, setup, run }: CardProps) {
  return (
    <section className="card">
      <div className="card-title">Rooms / areas</div>
      <table className="dt">
        <thead>
          <tr>
            <th>Name</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {setup.rooms.length === 0 && (
            <tr>
              <td colSpan={2} className="empty-cell">
                No rooms yet.
              </td>
            </tr>
          )}
          {setup.rooms.map((room) => (
            <tr key={room}>
              <td>
                <input
                  defaultValue={room}
                  onBlur={(e) => {
                    if (e.target.value !== room) {
                      run(() => withConfirmRetry(
                        () => api.renameRoom(projectId, room, e.target.value),
                        () => api.renameRoom(projectId, room, e.target.value),
                      ));
                    }
                  }}
                />
              </td>
              <td className="col-actions">
                <button
                  className="icon-btn"
                  title="Remove"
                  onClick={() =>
                    run(() =>
                      withConfirmRetry(
                        () => api.removeRoom(projectId, room),
                        (confirm) => api.removeRoom(projectId, room, confirm),
                      ),
                    )
                  }
                >
                  ✕
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <button
        className="btn-ghost"
        onClick={() => {
          const name = window.prompt("New room / area name:");
          if (name?.trim()) run(() => api.addRoom(projectId, name.trim()));
        }}
      >
        + Add room
      </button>
    </section>
  );
}

function PhasesCard({
  projectId,
  setup,
  run,
  onTransferDone,
  onTransferError,
}: CardProps & {
  onTransferDone: (result: TransferResult, mode: TransferMode) => void;
  onTransferError: (message: string) => void;
}) {
  return (
    <section className="card">
      <div className="card-title">
        Phases <span className="card-title-note">— now / next / later</span>
      </div>
      <table className="dt">
        <thead>
          <tr>
            <th></th>
            <th>Name</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {setup.phases.map((phase, i) => (
            <tr key={phase.id}>
              <td className="col-order">
                <button
                  className="icon-btn"
                  disabled={i === 0}
                  onClick={() => run(() => api.movePhase(projectId, i, -1))}
                >
                  ▲
                </button>
                <button
                  className="icon-btn"
                  disabled={i === setup.phases.length - 1}
                  onClick={() => run(() => api.movePhase(projectId, i, 1))}
                >
                  ▼
                </button>
              </td>
              <td>
                <input
                  defaultValue={phase.label}
                  onBlur={(e) => {
                    if (e.target.value.trim() && e.target.value !== phase.label) {
                      run(() => api.renamePhase(projectId, phase.id, e.target.value));
                    }
                  }}
                />
              </td>
              <td className="col-actions-2">
                <div className="actions-row">
                  <PhaseTransferMenu
                    projectId={projectId}
                    phaseId={phase.id}
                    onDone={onTransferDone}
                    onError={onTransferError}
                  />
                  <button
                    className="icon-btn"
                    title="Remove"
                    onClick={() =>
                      run(() =>
                        withConfirmRetry(
                          () => api.removePhase(projectId, phase.id),
                          (confirm) => api.removePhase(projectId, phase.id, confirm),
                        ),
                      )
                    }
                  >
                    ✕
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <button
        className="btn-ghost"
        onClick={() => {
          const label = window.prompt('New phase name (e.g. "Phase 4" or "Someday"):');
          if (label?.trim()) run(() => api.addPhase(projectId, label.trim()));
        }}
      >
        + Add phase
      </button>
    </section>
  );
}

/** A phase row's transfer action — resolves the phase's task ids lazily
 * (fetched fresh at click time, since SetupTab doesn't otherwise load
 * tasks) and offers copy/move to every other project or a new one. */
function PhaseTransferMenu({
  projectId,
  phaseId,
  onDone,
  onError,
}: {
  projectId: string;
  phaseId: number;
  onDone: (result: TransferResult, mode: TransferMode) => void;
  onError: (message: string) => void;
}) {
  const { data: projects } = useFetch(() => api.listProjects(), [projectId]);
  const others = (projects ?? []).filter((p) => p.id !== projectId);

  async function run(target: { targetProjectId: string } | { newProjectName: string }, mode: TransferMode) {
    try {
      const tasks = await api.getTasks(projectId);
      const taskIds = tasks.filter((t) => t.phase === phaseId).map((t) => t.task_id);
      if (taskIds.length === 0) {
        onError("This phase has no tasks to transfer.");
        return;
      }
      const result = await api.transferTasks(projectId, taskIds, target, mode);
      onDone(result, mode);
    } catch (e) {
      onError(e instanceof ApiError ? e.detail : String(e));
    }
  }

  const items = [
    ...others.flatMap((p) => [
      { label: `Copy → ${p.name}`, onSelect: () => run({ targetProjectId: p.id }, "copy" as TransferMode) },
      { label: `Move → ${p.name}`, onSelect: () => run({ targetProjectId: p.id }, "move" as TransferMode) },
    ]),
    {
      label: "Copy → New project…",
      onSelect: () => {
        const name = window.prompt("New project name:");
        if (name?.trim()) run({ newProjectName: name.trim() }, "copy");
      },
    },
    {
      label: "Move → New project…",
      onSelect: () => {
        const name = window.prompt("New project name:");
        if (name?.trim()) run({ newProjectName: name.trim() }, "move");
      },
    },
  ];

  return <Menu label="⇄" variant="icon" title="Transfer this phase's tasks" items={items} />;
}

function StagesCard({ projectId, setup, run }: CardProps) {
  return (
    <section className="card">
      <div className="card-title">
        Stages <span className="card-title-note">— trade execution order</span>
      </div>
      <table className="dt">
        <thead>
          <tr>
            <th></th>
            <th>#</th>
            <th>Name</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {setup.stages.map((stage, i) => (
            <tr key={stage.id}>
              <td className="col-order">
                <button
                  className="icon-btn"
                  disabled={i === 0}
                  onClick={() => run(() => api.moveStage(projectId, i, -1))}
                >
                  ▲
                </button>
                <button
                  className="icon-btn"
                  disabled={i === setup.stages.length - 1}
                  onClick={() => run(() => api.moveStage(projectId, i, 1))}
                >
                  ▼
                </button>
              </td>
              <td className="muted num">{i + 1}</td>
              <td>
                <input
                  defaultValue={stage.label}
                  onBlur={(e) => {
                    if (e.target.value.trim() && e.target.value !== stage.label) {
                      run(() => api.renameStage(projectId, stage.id, e.target.value));
                    }
                  }}
                />
              </td>
              <td className="col-actions">
                <button
                  className="icon-btn"
                  title="Remove"
                  onClick={() =>
                    run(() =>
                      withConfirmRetry(
                        () => api.removeStage(projectId, stage.id),
                        (confirm) => api.removeStage(projectId, stage.id, confirm),
                      ),
                    )
                  }
                >
                  ✕
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <button
        className="btn-ghost"
        onClick={() => {
          const label = window.prompt('New stage name (e.g. "Waterproofing"):');
          if (label?.trim()) run(() => api.addStage(projectId, label.trim()));
        }}
      >
        + Add stage
      </button>
    </section>
  );
}
