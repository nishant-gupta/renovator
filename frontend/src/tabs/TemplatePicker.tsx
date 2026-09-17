import { useState } from "react";
import { api, ApiError } from "../api/client";
import { useFetch } from "../api/hooks";
import { Modal } from "../components/Modal";
import type { Setup, TaskView } from "../api/types";

interface TemplatePickerProps {
  projectId: string;
  setup: Setup;
  onClose: () => void;
  onCreated: (tasks: TaskView[]) => void;
  onStartBlank: () => void;
}

/** feature.md §4.2 — a grid of common jobs that prefill category/trade/
 * structure/starting rate. Room and quantity are asked for here (a
 * lightweight stand-in for "you just set the room, name, quantity, and
 * dates" in the editor) rather than opening the full task editor first. */
export function TemplatePicker({ projectId, setup, onClose, onCreated, onStartBlank }: TemplatePickerProps) {
  const { data: templates, error, loading } = useFetch(() => api.listTemplates(projectId), [projectId]);
  const [pending, setPending] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  async function pick(templateId: string) {
    setFormError(null);
    const room = setup.rooms[0];
    if (!room) {
      setFormError("Add a room first (Setup tab) before using a template.");
      return;
    }
    const qtyStr = window.prompt(`Quantity (in the template's unit) for this job in "${room}":`, "");
    if (qtyStr === null) return;
    const qty = qtyStr.trim() ? Number(qtyStr) : undefined;
    setPending(templateId);
    try {
      const tasks = await api.instantiateTemplate(projectId, { template_id: templateId, room, qty });
      onCreated(tasks);
    } catch (e) {
      setFormError(e instanceof ApiError ? e.detail : String(e));
    } finally {
      setPending(null);
    }
  }

  return (
    <Modal
      title="Start from a template"
      onClose={onClose}
      footer={
        <>
          <div className="muted">or</div>
          <button className="btn-ghost" onClick={onStartBlank}>
            Start blank instead
          </button>
        </>
      }
    >
      <p className="page-sub modal-intro">
        Picks the right category, trade, and starting rate — you set the room and quantity, then adjust anything
        else before saving. New tasks go in "{setup.rooms[0] ?? "—"}"; change the room afterward if needed.
      </p>
      {formError && <div className="banner banner-error">{formError}</div>}
      {loading && <div className="empty">Loading…</div>}
      {error && <div className="empty empty-error">{error}</div>}
      {templates && (
        <div className="tpl-grid">
          {templates.map((tpl) => (
            <button key={tpl.id} className="tpl-card" disabled={pending !== null} onClick={() => pick(tpl.id)}>
              <span className="tpl-name">{pending === tpl.id ? "Adding…" : tpl.name}</span>
              <span className="tpl-meta">
                {tpl.category} · {tpl.structure === "split" ? "Material + Labour" : "Single line"}
              </span>
            </button>
          ))}
        </div>
      )}
    </Modal>
  );
}
