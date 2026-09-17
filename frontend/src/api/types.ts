// Mirrors the backend's Pydantic schema (backend/src/renovator/domain/models.py)
// and its API response shapes (backend/src/renovator/tools/read_tools.py,
// api/routes.py). Field names are kept snake_case — matching the JSON the
// API actually sends — rather than translated to camelCase, so there is no
// mapping layer to keep in sync as the backend evolves.

export type LineType = "Material" | "Labor" | "Inclusive";
export type CostMethod = "rate" | "custom";
export type BuyStatus = "To buy" | "Ordered" | "Delivered";
export type TaskStatus = "Not Started" | "In Progress" | "On Hold" | "Done";

export interface Rate {
  key: string;
  label: string;
  unit: string;
  value: number;
}

// ---- request bodies for tools/crud_tools.py's TaskInput/LineInput ---------

export interface LineInput {
  id?: string | null;
  worker_type?: string;
  status?: TaskStatus;
  cost_method?: CostMethod;
  rate_key?: string | null;
  qty?: number | null;
  custom_amount?: number | null;
  buy_status?: BuyStatus;
  depends_on?: string[];
  actual_cost?: number | null;
  notes?: string;
}

export interface TaskInput {
  task_id?: string | null;
  room: string;
  name: string;
  category: string;
  phase: number;
  stage_id?: number | null;
  mandatory?: boolean;
  duration_days?: number | null;
  start_override?: string | null;
  structure: "single" | "split";
  single_line_type?: LineType;
  single?: LineInput | null;
  material?: LineInput | null;
  labor?: LineInput | null;
}

export interface Template {
  id: string;
  name: string;
  category: string;
  unit: string;
  structure: "single" | "split";
}

// The categories the reference app's task editor offers (feature.md §4.1) —
// not enforced by the backend (category is a free string there), but a
// closed dropdown here beats a typo-prone free-text field.
export const CATEGORIES = [
  "Carpentry",
  "Furnishing",
  "Plumbing",
  "Electrical",
  "Tiling",
  "Civil",
  "Civil/POP",
  "Flooring",
  "Painting",
  "Civil/Carpentry",
  "Plumbing/Glasswork",
  "Other",
] as const;

export interface Phase {
  id: number;
  label: string;
}

export interface Stage {
  id: number;
  label: string;
}

export interface Setup {
  rooms: string[];
  rates: Rate[];
  phases: Phase[];
  stages: Stage[];
  project_start: string;
  work_weekends: boolean;
  sequence_stages: boolean;
}

export interface TaskLineView {
  line_id: string;
  line_type: LineType;
  worker_type: string;
  status: TaskStatus;
  cost_method: CostMethod;
  rate_key: string | null;
  qty: number | null;
  custom_amount: number | null;
  buy_status: BuyStatus;
  depends_on: string[];
  actual_cost: number | null;
  notes: string;
}

export interface TaskView {
  task_id: string;
  room: string;
  name: string;
  category: string;
  phase: number;
  stage_id: number | null;
  mandatory: boolean;
  duration_days: number | null;
  start_override: string | null;
  is_split: boolean;
  total_cost: number;
  lines: TaskLineView[];
}

export interface ScheduledTaskView {
  task_id: string;
  room: string;
  name: string;
  category: string;
  phase: number;
  stage_id: number | null;
  mandatory: boolean;
  is_split: boolean;
  total_cost: number;
  worker_type: string;
  start: string | null;
  end: string | null;
  duration_days: number | null;
  fixed_start: boolean;
}

export interface Schedule {
  project_start: string;
  project_end: string | null;
  tasks: ScheduledTaskView[];
}

export interface SuggestedOrderItem {
  line_id: string;
  room: string;
  name: string;
  line_type: LineType;
}

export interface MaterialLineView {
  line_id: string;
  name: string;
  room: string;
  need_by: string | null;
  overdue: boolean;
  qty: number | null;
  unit: string;
  cost: number;
  buy_status: BuyStatus;
  notes: string;
}

export interface MaterialsGroup {
  week_key: string;
  subtotal: number;
  lines: MaterialLineView[];
}

export interface MaterialsPlan {
  total: number;
  to_buy_cost: number;
  to_buy_count: number;
  ordered_count: number;
  delivered_count: number;
  groups: MaterialsGroup[];
}

export type SumPair = [string, number];

export interface EstimateTaskRow {
  task_id: string;
  room: string;
  name: string;
  is_split: boolean;
  total_cost: number;
}

export interface EstimateSummary {
  total: number;
  mandatory: number;
  optional: number;
  materials: number;
  by_room: SumPair[];
  by_trade: SumPair[];
  by_phase: SumPair[];
  tasks: EstimateTaskRow[];
}

export interface TrackTaskRow {
  task_id: string;
  room: string;
  name: string;
  is_split: boolean;
  total_cost: number;
  actual_cost: number | null;
  status: TaskStatus;
}

export interface TrackSummary {
  progress_pct: number;
  lines_done: number;
  lines_total: number;
  estimated_total: number;
  actual_total: number;
  actuals_logged: number;
  variance: number | null;
  tasks: TrackTaskRow[];
}

export interface ChangelogEntry {
  at: string;
  action: string;
  detail: string;
}

// ---- multi-project management (store/project_registry.py, tools/transfer_tools.py) ----

export interface ProjectSummary {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
}

export type TransferMode = "copy" | "move";

// ---- org-wide defaults new projects are seeded with (store/global_settings.py) ----

export interface GlobalSettings {
  work_weekends: boolean;
  sequence_stages: boolean;
  rates: Rate[];
}

// ---- agentic chat (agents/chat_stream.py, Phase 7) -------------------------

export interface ChatToolCall {
  name: string;
  args: Record<string, unknown>;
}

export interface ChatInterruptAction {
  name: string;
  args: Record<string, unknown>;
  description: string;
}

export type ChatEvent =
  | { type: "tool_call"; calls: ChatToolCall[] }
  | { type: "tool_result"; name: string; content: string }
  | { type: "message"; role: "user" | "assistant"; content: string; has_image?: boolean }
  | { type: "interrupt"; actions: ChatInterruptAction[] }
  | { type: "error"; message: string }
  | {
      type: "usage";
      duration_ms: number;
      total_input_tokens: number;
      total_output_tokens: number;
      estimated_cost_usd: number;
    }
  | { type: "done" };

export type ChatResumeDecision = { type: "approve" } | { type: "reject"; message: string };

// ---- Phase 9's local cost/latency dashboard (agents/chat_stream.py, store/plan_store.py) ----

export interface UsageByModel {
  model: string;
  calls: number;
  input_tokens: number;
  output_tokens: number;
}

export interface UsageSummary {
  total_calls: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_duration_ms: number;
  by_model: UsageByModel[];
  recent: { at: string; model: string; input_tokens: number; output_tokens: number; duration_ms: number }[];
}

export type PlanEvent = { type: "ready" } | { type: "changed"; updated_at: string };

export interface TransferResult {
  target_project_id: string;
  transferred_task_count: number;
  created_rooms: string[];
  created_rates: string[];
  created_phases: string[];
  created_stages: string[];
  dropped_dependencies: number;
}
