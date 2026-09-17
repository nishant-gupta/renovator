import { useState } from "react";
import { api, ApiError } from "../api/client";
import { useFetch } from "../api/hooks";
import { withConfirmRetry } from "../confirm";
import { Modal } from "./Modal";
import type { ProjectSummary, Setup } from "../api/types";

interface ProjectEditorProps {
  /** null => creating a new project; once created, the caller re-renders
   * this same modal with the new project so it flows straight into edit
   * mode without closing. */
  project: ProjectSummary | null;
  onClose: () => void;
  onCreated: (project: ProjectSummary) => void;
  /** Fired after a rename or a settings/rate-card edit, so the caller can
   * refresh its project list / top bar. */
  onChanged: () => void;
  onDeleted: () => void;
}

/** The "proper create/edit project page" — a real form instead of
 * window.prompt, covering the project's name plus the settings that seed
 * from the global defaults (timing flags, rate card) and everything else
 * that's specific to one project (not the structural rooms/phases/stages,
 * which stay on the Setup tab). */
export function ProjectEditor({ project, onClose, onCreated, onChanged, onDeleted }: ProjectEditorProps) {
  const isNew = project === null;
  const [name, setName] = useState(project?.name ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: setup, reload } = useFetch<Setup | null>(
    () => (project ? api.getSetup(project.id) : Promise.resolve(null)),
    [project?.id],
  );

  async function run(action: () => Promise<unknown>) {
    setError(null);
    try {
      await action();
      reload();
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
    }
  }

  async function create() {
    if (!name.trim()) {
      setError("Give the project a name first.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      onCreated(await api.createProject(name.trim()));
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
    } finally {
      setSaving(false);
    }
  }

  async function rename() {
    if (!project) return;
    const trimmed = name.trim();
    if (!trimmed || trimmed === project.name) return;
    setSaving(true);
    setError(null);
    try {
      await api.renameProject(project.id, trimmed);
      onChanged();
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
    } finally {
      setSaving(false);
    }
  }

  async function remove() {
    if (!project) return;
    setSaving(true);
    setError(null);
    try {
      await api.deleteProject(project.id);
      onDeleted();
    } catch (e) {
      if (e instanceof ApiError && e.needsConfirmation) {
        if (window.confirm(e.detail)) {
          try {
            await api.deleteProject(project.id, true);
            onDeleted();
            return;
          } catch (e2) {
            setError(e2 instanceof ApiError ? e2.detail : String(e2));
          }
        }
      } else {
        setError(e instanceof ApiError ? e.detail : String(e));
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal
      title={isNew ? "New project" : "Edit project"}
      onClose={onClose}
      footer={
        <>
          <div />
          <div className="row-actions">
            {!isNew && (
              <button className="btn-danger" disabled={saving} onClick={remove}>
                Delete project
              </button>
            )}
            <button className="btn-ghost" onClick={onClose}>
              {isNew ? "Cancel" : "Done"}
            </button>
            {isNew && (
              <button className="btn" disabled={saving} onClick={create}>
                Create
              </button>
            )}
          </div>
        </>
      }
    >
      {error && <div className="banner banner-error">{error}</div>}

      <label className="field field-wide">
        <span>Project name</span>
        <input
          type="text"
          value={name}
          autoFocus
          placeholder="e.g. Sunshine Reno"
          onChange={(e) => setName(e.target.value)}
          onBlur={() => {
            if (!isNew) rename();
          }}
        />
      </label>

      {project && (
        <p className="modal-meta">
          Created {project.created_at} · Last updated {project.updated_at}
        </p>
      )}

      {project && setup && (
        <>
          <div className="modal-section">Project timing</div>
          <div className="frow">
            <label className="field">
              <span>Project start date</span>
              <input
                type="date"
                defaultValue={setup.project_start}
                onChange={(e) => run(() => api.updateSettings(project.id, { project_start: e.target.value }))}
              />
            </label>
            <label className="field field-checkbox">
              <input
                type="checkbox"
                checked={setup.work_weekends}
                onChange={(e) => run(() => api.updateSettings(project.id, { work_weekends: e.target.checked }))}
              />
              <span>Work on weekends too</span>
            </label>
            <label className="field field-checkbox">
              <input
                type="checkbox"
                checked={setup.sequence_stages}
                onChange={(e) => run(() => api.updateSettings(project.id, { sequence_stages: e.target.checked }))}
              />
              <span>Run stages in order</span>
            </label>
          </div>

          <div className="modal-section">Rate card</div>
          <table className="dt">
            <thead>
              <tr>
                <th>Rate</th>
                <th>Unit</th>
                <th>₹ / unit</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {setup.rates.length === 0 && (
                <tr>
                  <td colSpan={4} className="empty-cell">
                    No rates yet.
                  </td>
                </tr>
              )}
              {setup.rates.map((rate) => (
                <tr key={rate.key}>
                  <td>{rate.label}</td>
                  <td className="muted">{rate.unit}</td>
                  <td>
                    <input
                      type="number"
                      defaultValue={rate.value}
                      onBlur={(e) => {
                        const value = Number(e.target.value) || 0;
                        if (value !== rate.value) run(() => api.updateRate(project.id, rate.key, value));
                      }}
                    />
                  </td>
                  <td className="col-actions">
                    <button
                      className="icon-btn"
                      title="Delete"
                      onClick={() =>
                        run(() =>
                          withConfirmRetry(
                            () => api.deleteRate(project.id, rate.key),
                            (confirm) => api.deleteRate(project.id, rate.key, confirm),
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
              const label = window.prompt('New rate name (e.g. "Waterproofing — sqft"):');
              if (!label?.trim()) return;
              const unit = window.prompt("Unit (sqft / running ft / point / fixture / lumpsum):", "sqft") ?? "sqft";
              const value = Number(window.prompt("₹ per unit:", "0")) || 0;
              run(() => api.addRate(project.id, label.trim(), unit, value));
            }}
          >
            + Add rate
          </button>
        </>
      )}
    </Modal>
  );
}
