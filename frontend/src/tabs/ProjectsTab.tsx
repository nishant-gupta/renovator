import { Fragment, useState } from "react";
import { api, ApiError } from "../api/client";
import { useFetch } from "../api/hooks";
import { ProjectEditor } from "../components/ProjectEditor";
import type { ProjectSummary } from "../api/types";

interface ProjectsTabProps {
  projects: ProjectSummary[];
  activeProjectId: string | null;
  onOpen: (id: string) => void;
  onProjectsChanged: (nextActiveId?: string) => void;
}

export function ProjectsTab({ projects, activeProjectId, onOpen, onProjectsChanged }: ProjectsTabProps) {
  const { data: globalSettings, error, loading, reload } = useFetch(() => api.getGlobalSettings(), []);
  const [globalError, setGlobalError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [editing, setEditing] = useState<ProjectSummary | "new" | null>(null);

  async function runGlobal(action: () => Promise<unknown>) {
    setGlobalError(null);
    try {
      await action();
      reload();
    } catch (e) {
      setGlobalError(e instanceof ApiError ? e.detail : String(e));
    }
  }

  function toggleExpand(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  if (loading) return <div className="empty">Loading…</div>;
  if (error) return <div className="empty empty-error">Couldn't load global defaults: {error}</div>;
  if (!globalSettings) return null;

  return (
    <div>
      <h1 className="page-h">Projects</h1>
      <p className="page-sub">Create, open, and manage every project — plus the global defaults new ones start from.</p>

      {globalError && <div className="banner banner-error">{globalError}</div>}

      <section className="card">
        <div className="card-title">
          Global defaults
          <span className="card-title-note">
            {" "}
            — seed new projects only; editing these never changes a project that already exists
          </span>
        </div>
        <div className="frow">
          <label className="field field-checkbox">
            <input
              type="checkbox"
              checked={globalSettings.work_weekends}
              onChange={(e) => runGlobal(() => api.updateGlobalSettings({ work_weekends: e.target.checked }))}
            />
            <span>Work on weekends too</span>
          </label>
          <label className="field field-checkbox">
            <input
              type="checkbox"
              checked={globalSettings.sequence_stages}
              onChange={(e) => runGlobal(() => api.updateGlobalSettings({ sequence_stages: e.target.checked }))}
            />
            <span>Run stages in order</span>
          </label>
        </div>

        <div className="modal-section">Default rate card</div>
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
            {globalSettings.rates.length === 0 && (
              <tr>
                <td colSpan={4} className="empty-cell">
                  No default rates yet.
                </td>
              </tr>
            )}
            {globalSettings.rates.map((rate) => (
              <tr key={rate.key}>
                <td>{rate.label}</td>
                <td className="muted">{rate.unit}</td>
                <td>
                  <input
                    type="number"
                    defaultValue={rate.value}
                    onBlur={(e) => {
                      const value = Number(e.target.value) || 0;
                      if (value !== rate.value) runGlobal(() => api.updateGlobalRate(rate.key, value));
                    }}
                  />
                </td>
                <td className="col-actions">
                  <button
                    className="icon-btn"
                    title="Delete"
                    onClick={() => runGlobal(() => api.deleteGlobalRate(rate.key))}
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
            const label = window.prompt('New default rate name (e.g. "Waterproofing — sqft"):');
            if (!label?.trim()) return;
            const unit = window.prompt("Unit (sqft / running ft / point / fixture / lumpsum):", "sqft") ?? "sqft";
            const value = Number(window.prompt("₹ per unit:", "0")) || 0;
            runGlobal(() => api.addGlobalRate(label.trim(), unit, value));
          }}
        >
          + Add default rate
        </button>
      </section>

      <section className="card">
        <div className="card-title">
          All projects <span className="card-title-note">— open one to work on it, or edit its settings</span>
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
            {projects.length === 0 && (
              <tr>
                <td colSpan={3} className="empty-cell">
                  No projects yet.
                </td>
              </tr>
            )}
            {projects.map((p) => (
              <Fragment key={p.id}>
                <tr>
                  <td className="col-order">
                    <button className="icon-btn" onClick={() => toggleExpand(p.id)}>
                      {expanded.has(p.id) ? "▾" : "▸"}
                    </button>
                  </td>
                  <td>
                    {p.name} {p.id === activeProjectId && <span className="tag tag-active">Active</span>}
                  </td>
                  <td className="col-actions-2">
                    <div className="actions-row">
                      <button className="btn-ghost" onClick={() => onOpen(p.id)}>
                        Open
                      </button>
                      <button className="icon-btn" title="Edit project" onClick={() => setEditing(p)}>
                        ✎
                      </button>
                    </div>
                  </td>
                </tr>
                {expanded.has(p.id) && (
                  <tr className="dt-subrow">
                    <td></td>
                    <td colSpan={2}>
                      Created {p.created_at} · Last updated {p.updated_at}
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
        <button className="btn-ghost" onClick={() => setEditing("new")}>
          + New project
        </button>
      </section>

      {editing && (
        <ProjectEditor
          project={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onCreated={(created) => {
            onProjectsChanged(created.id);
            setEditing(created);
          }}
          onChanged={() => onProjectsChanged()}
          onDeleted={() => {
            setEditing(null);
            onProjectsChanged();
          }}
        />
      )}
    </div>
  );
}
