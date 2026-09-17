import { useState } from "react";
import { api, ApiError } from "../api/client";
import { tradeBucket, tradeColorVar } from "../trade";
import { money } from "../format";
import type { ScheduledTaskView, Stage, SuggestedOrderItem } from "../api/types";

interface BoardViewProps {
  projectId: string;
  tasks: ScheduledTaskView[];
  stages: Stage[];
  onOpenTask: (taskId: string) => void;
  onAddToStage: (stageId: number | null) => void;
  onChanged: () => void;
  onReorderStages: (fromIndex: number, toIndex: number) => Promise<void>;
}

/** Cards omit the "after: X" dependency note the reference app shows
 * (feature.md §5.3) — that needs each line's depends_on, which the
 * Schedule view's task-level data doesn't carry; dependency display/editing
 * is still open work (see design doc Phase 6c). */
export function BoardView({ projectId, tasks, stages, onOpenTask, onAddToStage, onChanged, onReorderStages }: BoardViewProps) {
  const [dragTaskId, setDragTaskId] = useState<string | null>(null);
  const [dragStageIndex, setDragStageIndex] = useState<number | null>(null);
  const [dropTarget, setDropTarget] = useState<number | null>(null);
  const [showOrder, setShowOrder] = useState(false);
  const [order, setOrder] = useState<SuggestedOrderItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function toggleOrder() {
    if (showOrder) {
      setShowOrder(false);
      return;
    }
    try {
      const items = await api.getSuggestedOrder(projectId);
      setOrder(items);
      setShowOrder(true);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
    }
  }

  async function moveTaskToStage(taskId: string, stageId: number | null) {
    setError(null);
    try {
      await api.moveTasksToStage(projectId, [taskId], stageId);
      onChanged();
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
    }
  }

  function card(t: ScheduledTaskView) {
    const color = tradeColorVar(tradeBucket(t.worker_type || t.category).key);
    return (
      <div
        key={t.task_id}
        className="tcard"
        style={{ borderLeftColor: color }}
        draggable
        onDragStart={() => setDragTaskId(t.task_id)}
        onDragOver={(e) => e.preventDefault()}
        onClick={() => onOpenTask(t.task_id)}
      >
        <div className="tcard-name">{t.name}</div>
        <div className="tcard-meta">
          {t.room} · {t.duration_days ?? 1}d
        </div>
        <div className="tcard-cost">{money(t.total_cost)}</div>
      </div>
    );
  }

  function column(stageId: number | null, label: string, ts: ScheduledTaskView[], index: number | null) {
    const total = ts.reduce((s, t) => s + t.total_cost, 0);
    const isDropTarget = dropTarget === (stageId ?? -1);
    return (
      <div
        key={label}
        className={`board-col ${isDropTarget ? "drop-target" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDropTarget(stageId ?? -1);
        }}
        onDragLeave={() => setDropTarget(null)}
        onDrop={(e) => {
          e.preventDefault();
          setDropTarget(null);
          if (dragStageIndex !== null && index !== null) {
            onReorderStages(dragStageIndex, index);
            setDragStageIndex(null);
          } else if (dragTaskId) {
            moveTaskToStage(dragTaskId, stageId);
            setDragTaskId(null);
          }
        }}
      >
        <div
          className="row between board-col-head"
          draggable={index !== null}
          onDragStart={() => index !== null && setDragStageIndex(index)}
        >
          <h3>{label}</h3>
        </div>
        <div className="board-col-total">
          {ts.length} item{ts.length === 1 ? "" : "s"} · {money(total)}
        </div>
        {ts.length ? ts.map(card) : <div className="empty">Drop tasks here</div>}
        <button className="btn-ghost board-col-add" onClick={() => onAddToStage(stageId)}>
          + Add here
        </button>
      </div>
    );
  }

  const stageIds = new Set(stages.map((s) => s.id));
  const unassigned = tasks.filter((t) => t.stage_id == null || !stageIds.has(t.stage_id));

  return (
    <div>
      {error && <div className="banner banner-error">{error}</div>}
      <div className="tab-toolbar">
        <button className="btn-ghost" onClick={toggleOrder}>
          {showOrder ? "Hide" : "Show"} suggested order
        </button>
      </div>
      {showOrder && order && (
        <div className="card">
          <div className="card-title">Suggested execution order</div>
          <p className="muted order-hint">Dependencies first, stage order breaks ties. Unrelated items can run in parallel.</p>
          <ol className="orderlist">
            {order.map((item) => (
              <li key={item.line_id}>
                {item.room} — {item.name} <span className="tag tag-muted">{item.line_type}</span>
              </li>
            ))}
          </ol>
        </div>
      )}
      <div className="board">
        {stages.map((stage, i) => column(stage.id, stage.label, tasks.filter((t) => t.stage_id === stage.id), i))}
        {unassigned.length > 0 && column(null, "Unassigned", unassigned, null)}
      </div>
    </div>
  );
}
