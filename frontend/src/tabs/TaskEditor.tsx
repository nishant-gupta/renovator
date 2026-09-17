import { useState } from "react";
import { api, ApiError } from "../api/client";
import { useFetch } from "../api/hooks";
import { Modal } from "../components/Modal";
import { TransferMenu } from "../components/TransferMenu";
import { CATEGORIES } from "../api/types";
import type {
  BuyStatus,
  CostMethod,
  LineInput,
  LineType,
  Setup,
  TaskInput,
  TaskStatus,
  TaskView,
} from "../api/types";
import { money } from "../format";

const STATUSES: TaskStatus[] = ["Not Started", "In Progress", "On Hold", "Done"];
const BUY_STATUSES: BuyStatus[] = ["To buy", "Ordered", "Delivered"];
const LINE_TYPES: LineType[] = ["Material", "Labor", "Inclusive"];

interface EditableLine {
  id?: string | null;
  worker_type: string;
  status: TaskStatus;
  cost_method: CostMethod;
  rate_key: string;
  qty: string;
  custom_amount: string;
  buy_status: BuyStatus;
  actual_cost: string;
  notes: string;
  depends_on: string[];
}

function blankLine(): EditableLine {
  return {
    worker_type: "",
    status: "Not Started",
    cost_method: "custom",
    rate_key: "",
    qty: "",
    custom_amount: "",
    buy_status: "To buy",
    actual_cost: "",
    notes: "",
    depends_on: [],
  };
}

function lineFromView(line?: TaskView["lines"][number]): EditableLine {
  if (!line) return blankLine();
  return {
    id: line.line_id,
    worker_type: line.worker_type,
    status: line.status,
    cost_method: line.cost_method,
    rate_key: line.rate_key ?? "",
    qty: line.qty != null ? String(line.qty) : "",
    custom_amount: line.custom_amount != null ? String(line.custom_amount) : "",
    buy_status: line.buy_status,
    actual_cost: line.actual_cost != null ? String(line.actual_cost) : "",
    notes: line.notes,
    depends_on: line.depends_on,
  };
}

function toLineInput(line: EditableLine): LineInput {
  return {
    id: line.id ?? undefined,
    worker_type: line.worker_type,
    status: line.status,
    cost_method: line.cost_method,
    rate_key: line.cost_method === "rate" ? line.rate_key || null : null,
    qty: line.cost_method === "rate" && line.qty !== "" ? Number(line.qty) : null,
    custom_amount: line.cost_method === "custom" && line.custom_amount !== "" ? Number(line.custom_amount) : null,
    buy_status: line.buy_status,
    actual_cost: line.actual_cost !== "" ? Number(line.actual_cost) : null,
    notes: line.notes,
    depends_on: line.depends_on,
  };
}

function lineCost(line: EditableLine, setup: Setup): number {
  if (line.cost_method === "rate") {
    const rate = setup.rates.find((r) => r.key === line.rate_key);
    return (rate?.value ?? 0) * (Number(line.qty) || 0);
  }
  return Number(line.custom_amount) || 0;
}

interface TaskEditorProps {
  projectId: string;
  setup: Setup;
  task: TaskView | null; // null => creating a new task
  presetStageId?: number | null; // only used when creating a new task (e.g. Board's "+ Add here")
  onClose: () => void;
  onSaved: (tasks: TaskView[]) => void;
}

export function TaskEditor({ projectId, setup, task, presetStageId, onClose, onSaved }: TaskEditorProps) {
  const isNew = task === null;
  const primary = task ? (task.is_split ? task.lines.find((l) => l.line_type === "Labor") : task.lines[0]) : undefined;

  // For the "Depends on" checklist (feature.md §4.1) — every other task's
  // lines, excluding this task's own (a line can't depend on itself or a
  // sibling of the same task).
  const { data: allTasks } = useFetch(() => api.getTasks(projectId), [projectId]);
  const otherLines = (allTasks ?? [])
    .filter((t) => t.task_id !== task?.task_id)
    .flatMap((t) => t.lines.map((l) => ({ line_id: l.line_id, room: t.room, name: t.name, line_type: l.line_type })));

  const [room, setRoom] = useState(task?.room ?? setup.rooms[0] ?? "");
  const [name, setName] = useState(task?.name ?? "");
  const [category, setCategory] = useState(task?.category ?? "Carpentry");
  const [phase, setPhase] = useState(task?.phase ?? setup.phases[0]?.id ?? 1);
  const [stageId, setStageId] = useState<number | null>(task?.stage_id ?? presetStageId ?? null);
  const [mandatory, setMandatory] = useState(task?.mandatory ?? true);
  const [durationDays, setDurationDays] = useState(task?.duration_days != null ? String(task.duration_days) : "");
  const [startOverride, setStartOverride] = useState(task?.start_override ?? "");
  const [isSplit, setIsSplit] = useState(task?.is_split ?? false);
  const [singleLineType, setSingleLineType] = useState<LineType>(
    !isNew && !task?.is_split ? primary?.line_type ?? "Inclusive" : "Inclusive",
  );

  const [single, setSingle] = useState<EditableLine>(!task?.is_split ? lineFromView(primary) : blankLine());
  const [material, setMaterial] = useState<EditableLine>(
    task?.is_split ? lineFromView(task.lines.find((l) => l.line_type === "Material")) : blankLine(),
  );
  const [labor, setLabor] = useState<EditableLine>(
    task?.is_split ? lineFromView(task.lines.find((l) => l.line_type === "Labor")) : blankLine(),
  );

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const cost = isSplit ? lineCost(material, setup) + lineCost(labor, setup) : lineCost(single, setup);

  async function save() {
    if (!name.trim()) {
      setError("Give the task a name first.");
      return;
    }
    const body: TaskInput = {
      task_id: task?.task_id ?? undefined,
      room,
      name: name.trim(),
      category,
      phase,
      stage_id: stageId,
      mandatory,
      duration_days: durationDays !== "" ? Number(durationDays) : null,
      start_override: startOverride || null,
      structure: isSplit ? "split" : "single",
      single_line_type: singleLineType,
      single: isSplit ? null : toLineInput(single),
      material: isSplit ? toLineInput(material) : null,
      labor: isSplit ? toLineInput(labor) : null,
    };
    setSaving(true);
    setError(null);
    try {
      const tasks = isNew
        ? await api.createTask(projectId, body)
        : await api.updateTask(projectId, task.task_id, body);
      onSaved(tasks);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
    } finally {
      setSaving(false);
    }
  }

  async function afterTransfer() {
    setError(null);
    onSaved(await api.getTasks(projectId));
  }

  async function remove() {
    if (!task) return;
    setSaving(true);
    setError(null);
    try {
      const tasks = await api.deleteTask(projectId, task.task_id);
      onSaved(tasks);
    } catch (e) {
      if (e instanceof ApiError && e.needsConfirmation) {
        if (window.confirm(e.detail)) {
          try {
            const tasks = await api.deleteTask(projectId, task.task_id, true);
            onSaved(tasks);
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
      title={isNew ? "Add task" : "Edit task"}
      onClose={onClose}
      footer={
        <>
          <div>
            Cost: <span className="preview-cost">{money(cost)}</span>
          </div>
          <div className="row-actions">
            {!isNew && (
              <TransferMenu
                projectId={projectId}
                resolveTaskIds={() => Promise.resolve([task.task_id])}
                onDone={afterTransfer}
                onError={setError}
              />
            )}
            {!isNew && (
              <button className="btn-danger" disabled={saving} onClick={remove}>
                Delete
              </button>
            )}
            <button className="btn-ghost" onClick={onClose}>
              Cancel
            </button>
            <button className="btn" disabled={saving} onClick={save}>
              Save
            </button>
          </div>
        </>
      }
    >
      {error && <div className="banner banner-error">{error}</div>}

      <div className="frow">
        <label className="field">
          <span>Room / Area</span>
          <select value={room} onChange={(e) => setRoom(e.target.value)}>
            {setup.rooms.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Category</span>
          <select value={category} onChange={(e) => setCategory(e.target.value)}>
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>
      </div>

      <label className="field field-wide">
        <span>Task name</span>
        <input
          type="text"
          value={name}
          placeholder="e.g. Re-tile bathroom wall"
          onChange={(e) => setName(e.target.value)}
          autoFocus={isNew}
        />
      </label>

      <label className="field field-wide">
        <span>Structure</span>
        <div className="radios">
          <label>
            <input type="radio" checked={!isSplit} onChange={() => setIsSplit(false)} /> Single line
          </label>
          <label>
            <input type="radio" checked={isSplit} onChange={() => setIsSplit(true)} /> Material + Labour (together)
          </label>
        </div>
      </label>

      <div className="frow">
        <label className="field">
          <span>Stage (execution order)</span>
          <select
            value={stageId ?? ""}
            onChange={(e) => setStageId(e.target.value === "" ? null : Number(e.target.value))}
          >
            <option value="">— No stage —</option>
            {setup.stages.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Phase</span>
          <select value={phase} onChange={(e) => setPhase(Number(e.target.value))}>
            {setup.phases.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Flag</span>
          <select value={mandatory ? "m" : "o"} onChange={(e) => setMandatory(e.target.value === "m")}>
            <option value="m">Mandatory</option>
            <option value="o">Optional</option>
          </select>
        </label>
      </div>

      <div className="frow">
        <label className="field">
          <span>Duration (working days)</span>
          <input
            type="number"
            min={1}
            value={durationDays}
            placeholder="auto"
            onChange={(e) => setDurationDays(e.target.value)}
          />
        </label>
        <label className="field">
          <span>Fixed start date (optional)</span>
          <input type="date" value={startOverride} onChange={(e) => setStartOverride(e.target.value)} />
        </label>
      </div>

      {isSplit ? (
        <>
          <div className="modal-section">Material</div>
          <LineFields line={material} onChange={setMaterial} setup={setup} isMaterial showDeps={false} otherLines={otherLines} />
          <div className="modal-section">Labor</div>
          <LineFields line={labor} onChange={setLabor} setup={setup} isMaterial={false} showDeps otherLines={otherLines} />
        </>
      ) : (
        <>
          <label className="field field-wide">
            <span>Line type</span>
            <div className="radios">
              {LINE_TYPES.map((lt) => (
                <label key={lt}>
                  <input type="radio" checked={singleLineType === lt} onChange={() => setSingleLineType(lt)} /> {lt}
                </label>
              ))}
            </div>
          </label>
          <LineFields
            line={single}
            onChange={setSingle}
            setup={setup}
            isMaterial={singleLineType === "Material"}
            showDeps
            otherLines={otherLines}
          />
        </>
      )}
    </Modal>
  );
}

interface OtherLine {
  line_id: string;
  room: string;
  name: string;
  line_type: LineType;
}

function LineFields({
  line,
  onChange,
  setup,
  isMaterial,
  showDeps,
  otherLines,
}: {
  line: EditableLine;
  onChange: (line: EditableLine) => void;
  setup: Setup;
  isMaterial: boolean;
  showDeps: boolean;
  otherLines: OtherLine[];
}) {
  const set = <K extends keyof EditableLine>(key: K, value: EditableLine[K]) => onChange({ ...line, [key]: value });

  function toggleDep(lineId: string, checked: boolean) {
    const next = checked ? [...line.depends_on, lineId] : line.depends_on.filter((id) => id !== lineId);
    set("depends_on", next);
  }

  return (
    <>
      <div className="frow">
        <label className="field">
          <span>Worker / Trade</span>
          <input type="text" value={line.worker_type} onChange={(e) => set("worker_type", e.target.value)} />
        </label>
        <label className="field">
          <span>Status</span>
          <select value={line.status} onChange={(e) => set("status", e.target.value as TaskStatus)}>
            {STATUSES.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </label>
      </div>

      <label className="field field-wide">
        <span>Costing method</span>
        <div className="radios">
          <label>
            <input
              type="radio"
              checked={line.cost_method === "rate"}
              onChange={() => set("cost_method", "rate")}
            />{" "}
            Rate card × quantity
          </label>
          <label>
            <input
              type="radio"
              checked={line.cost_method === "custom"}
              onChange={() => set("cost_method", "custom")}
            />{" "}
            Flat / quoted amount
          </label>
        </div>
      </label>

      {line.cost_method === "rate" ? (
        <div className="frow">
          <label className="field">
            <span>Rate</span>
            <select value={line.rate_key} onChange={(e) => set("rate_key", e.target.value)}>
              <option value="">— pick a rate —</option>
              {setup.rates.map((r) => (
                <option key={r.key} value={r.key}>
                  {r.label} (₹{r.value}/{r.unit})
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Quantity</span>
            <input type="number" value={line.qty} onChange={(e) => set("qty", e.target.value)} />
          </label>
        </div>
      ) : (
        <label className="field field-wide">
          <span>Amount (₹)</span>
          <input type="number" value={line.custom_amount} onChange={(e) => set("custom_amount", e.target.value)} />
        </label>
      )}

      {isMaterial && (
        <label className="field field-wide">
          <span>Procurement status</span>
          <select value={line.buy_status} onChange={(e) => set("buy_status", e.target.value as BuyStatus)}>
            {BUY_STATUSES.map((b) => (
              <option key={b}>{b}</option>
            ))}
          </select>
        </label>
      )}

      {showDeps && (
        <label className="field field-wide">
          <span>Depends on (must finish first)</span>
          <div className="deplist">
            {otherLines.length === 0 && <div className="muted">No other items yet.</div>}
            {otherLines.map((other) => (
              <label key={other.line_id} className="deplist-item">
                <input
                  type="checkbox"
                  checked={line.depends_on.includes(other.line_id)}
                  onChange={(e) => toggleDep(other.line_id, e.target.checked)}
                />
                {other.room} — {other.name} <span className="muted">({other.line_type})</span>
              </label>
            ))}
          </div>
        </label>
      )}

      <div className="frow">
        <label className="field">
          <span>Actual cost (₹, optional)</span>
          <input type="number" value={line.actual_cost} onChange={(e) => set("actual_cost", e.target.value)} />
        </label>
        <label className="field">
          <span>Notes</span>
          <input type="text" value={line.notes} onChange={(e) => set("notes", e.target.value)} />
        </label>
      </div>
    </>
  );
}
