import type {
  BuyStatus,
  ChangelogEntry,
  ChatEvent,
  ChatResumeDecision,
  EstimateSummary,
  GlobalSettings,
  MaterialsPlan,
  PlanEvent,
  ProjectSummary,
  Schedule,
  Setup,
  SuggestedOrderItem,
  TaskInput,
  TaskStatus,
  TaskView,
  Template,
  TrackSummary,
  TransferMode,
  TransferResult,
  UsageSummary,
} from "./types";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

/** Thrown on any non-2xx response. `status` 400 = ValidationError (hard
 * reject, don't retry as-is); 409 = ConfirmationRequired (the reference
 * app's confirm() dialogs — re-issue the same call with confirm=true if
 * the user agrees). See backend/src/renovator/tools/errors.py. */
export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }

  get needsConfirmation(): boolean {
    return this.status === 409;
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = data.detail ?? detail;
    } catch {
      // response wasn't JSON; fall back to statusText
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

function withConfirm(path: string, confirm: boolean): string {
  return confirm ? `${path}?confirm=true` : path;
}

export const api = {
  getHealth: () => request<{ status: string; has_llm_key: boolean }>("GET", "/health"),

  // ---- reads ----------------------------------------------------------
  getSetup: (projectId: string) => request<Setup>("GET", `/projects/${projectId}/setup`),
  getTasks: (projectId: string) => request<TaskView[]>("GET", `/projects/${projectId}/tasks`),
  getSchedule: (projectId: string) => request<Schedule>("GET", `/projects/${projectId}/schedule`),
  getSuggestedOrder: (projectId: string) =>
    request<SuggestedOrderItem[]>("GET", `/projects/${projectId}/suggested-order`),
  getMaterials: (projectId: string) => request<MaterialsPlan>("GET", `/projects/${projectId}/materials`),
  getEstimate: (projectId: string) => request<EstimateSummary>("GET", `/projects/${projectId}/estimate`),
  getTrack: (projectId: string) => request<TrackSummary>("GET", `/projects/${projectId}/track`),
  getChangelog: (projectId: string, limit = 50) =>
    request<ChangelogEntry[]>("GET", `/projects/${projectId}/changelog?limit=${limit}`),

  // ---- rooms ------------------------------------------------------------
  addRoom: (projectId: string, name: string) =>
    request<Setup>("POST", `/projects/${projectId}/rooms`, { name }),
  renameRoom: (projectId: string, name: string, newName: string) =>
    request<Setup>("PATCH", `/projects/${projectId}/rooms/${encodeURIComponent(name)}`, {
      new_name: newName,
    }),
  removeRoom: (projectId: string, name: string, confirm = false) =>
    request<Setup>(
      "DELETE",
      withConfirm(`/projects/${projectId}/rooms/${encodeURIComponent(name)}`, confirm),
    ),

  // ---- rates ------------------------------------------------------------
  addRate: (projectId: string, label: string, unit: string, value: number) =>
    request<Setup>("POST", `/projects/${projectId}/rates`, { label, unit, value }),
  updateRate: (projectId: string, key: string, value: number) =>
    request<Setup>("PATCH", `/projects/${projectId}/rates/${encodeURIComponent(key)}`, { value }),
  deleteRate: (projectId: string, key: string, confirm = false) =>
    request<Setup>(
      "DELETE",
      withConfirm(`/projects/${projectId}/rates/${encodeURIComponent(key)}`, confirm),
    ),

  // ---- phases ------------------------------------------------------------
  addPhase: (projectId: string, label: string) =>
    request<Setup>("POST", `/projects/${projectId}/phases`, { label }),
  renamePhase: (projectId: string, phaseId: number, label: string) =>
    request<Setup>("PATCH", `/projects/${projectId}/phases/${phaseId}`, { label }),
  removePhase: (projectId: string, phaseId: number, confirm = false) =>
    request<Setup>("DELETE", withConfirm(`/projects/${projectId}/phases/${phaseId}`, confirm)),
  movePhase: (projectId: string, index: number, direction: 1 | -1) =>
    request<Setup>("POST", `/projects/${projectId}/phases/reorder`, { index, direction }),

  // ---- stages ------------------------------------------------------------
  addStage: (projectId: string, label: string) =>
    request<Setup>("POST", `/projects/${projectId}/stages`, { label }),
  renameStage: (projectId: string, stageId: number, label: string) =>
    request<Setup>("PATCH", `/projects/${projectId}/stages/${stageId}`, { label }),
  removeStage: (projectId: string, stageId: number, confirm = false) =>
    request<Setup>("DELETE", withConfirm(`/projects/${projectId}/stages/${stageId}`, confirm)),
  moveStage: (projectId: string, index: number, direction: 1 | -1) =>
    request<Setup>("POST", `/projects/${projectId}/stages/reorder`, { index, direction }),

  // ---- project settings ----------------------------------------------------
  updateSettings: (
    projectId: string,
    settings: Partial<{ project_start: string; work_weekends: boolean; sequence_stages: boolean }>,
  ) => request<Setup>("PATCH", `/projects/${projectId}/settings`, settings),

  // ---- tasks (feature.md §4) --------------------------------------------------
  listTemplates: (projectId: string) => request<Template[]>("GET", `/projects/${projectId}/templates`),
  instantiateTemplate: (
    projectId: string,
    body: { template_id: string; room: string; name?: string; qty?: number; phase?: number; stage_id?: number | null },
  ) => request<TaskView[]>("POST", `/projects/${projectId}/tasks/from-template`, body),
  createTask: (projectId: string, task: TaskInput) =>
    request<TaskView[]>("POST", `/projects/${projectId}/tasks`, task),
  updateTask: (projectId: string, taskId: string, task: TaskInput) =>
    request<TaskView[]>("PATCH", `/projects/${projectId}/tasks/${taskId}`, task),
  deleteTask: (projectId: string, taskId: string, confirm = false) =>
    request<TaskView[]>("DELETE", withConfirm(`/projects/${projectId}/tasks/${taskId}`, confirm)),
  updateLine: (
    projectId: string,
    lineId: string,
    body: Partial<{ buy_status: BuyStatus; status: TaskStatus; actual_cost: number; notes: string }>,
  ) => request<TaskView[]>("PATCH", `/projects/${projectId}/lines/${lineId}`, body),
  moveTasksToStage: (projectId: string, taskIds: string[], stageId: number | null) =>
    request<Schedule>("POST", `/projects/${projectId}/tasks/move-to-stage`, { task_ids: taskIds, stage_id: stageId }),
  bulkSetMandatory: (projectId: string, taskIds: string[], mandatory: boolean) =>
    request<TaskView[]>("POST", `/projects/${projectId}/tasks/bulk-mandatory`, { task_ids: taskIds, mandatory }),
  bulkMoveToPhase: (projectId: string, taskIds: string[], phaseId: number) =>
    request<TaskView[]>("POST", `/projects/${projectId}/tasks/bulk-phase`, { task_ids: taskIds, phase_id: phaseId }),
  bulkDeleteTasks: (projectId: string, taskIds: string[], confirm = false) =>
    request<TaskView[]>(
      "POST",
      withConfirm(`/projects/${projectId}/tasks/bulk-delete`, confirm),
      { task_ids: taskIds },
    ),

  // ---- project management (multi-project) ------------------------------
  listProjects: () => request<ProjectSummary[]>("GET", "/projects"),
  createProject: (name: string) => request<ProjectSummary>("POST", "/projects", { name }),
  renameProject: (projectId: string, name: string) =>
    request<ProjectSummary>("PATCH", `/projects/${projectId}`, { name }),
  deleteProject: (projectId: string, confirm = false) =>
    request<{ ok: true }>("DELETE", withConfirm(`/projects/${projectId}`, confirm)),
  transferTasks: (
    projectId: string,
    taskIds: string[],
    target: { targetProjectId: string } | { newProjectName: string },
    mode: TransferMode,
  ) =>
    request<TransferResult>("POST", `/projects/${projectId}/tasks/transfer`, {
      task_ids: taskIds,
      mode,
      ...("targetProjectId" in target
        ? { target_project_id: target.targetProjectId }
        : { new_project_name: target.newProjectName }),
    }),

  // ---- global defaults (seed new projects only, never live) -------------
  getGlobalSettings: () => request<GlobalSettings>("GET", "/settings/global"),
  updateGlobalSettings: (patch: Partial<{ work_weekends: boolean; sequence_stages: boolean }>) =>
    request<GlobalSettings>("PATCH", "/settings/global", patch),
  addGlobalRate: (label: string, unit: string, value: number) =>
    request<GlobalSettings>("POST", "/settings/global/rates", { label, unit, value }),
  updateGlobalRate: (key: string, value: number) =>
    request<GlobalSettings>("PATCH", `/settings/global/rates/${encodeURIComponent(key)}`, { value }),
  deleteGlobalRate: (key: string) =>
    request<GlobalSettings>("DELETE", `/settings/global/rates/${encodeURIComponent(key)}`),

  // ---- agentic chat + plan-change stream (Phase 7) -----------------------
  /** Replays a thread's checkpointed history — including a still-pending
   * interrupt, if any — so the chat panel can recover its transcript (and
   * an in-flight approve/reject prompt) after a page reload. */
  getChatHistory: (projectId: string) => request<{ events: ChatEvent[] }>("GET", `/projects/${projectId}/chat/history`),

  /** Phase 9's local cost/latency dashboard data — cumulative, not just
   * this session's, and main-agent calls only (see chat_stream.py's
   * docstring for the sub-agent-usage gap). */
  getUsage: (projectId: string) => request<UsageSummary>("GET", `/projects/${projectId}/usage`),

  streamChat: async (
    projectId: string,
    // `image` is a data: URL (FileReader.readAsDataURL output) — a room
    // photo attached alongside (or instead of) a text message, Phase 8.
    body: { message: string; image?: string } | { resume: { decisions: ChatResumeDecision[] } },
    onEvent: (event: ChatEvent) => void,
  ): Promise<void> => {
    const res = await fetch(`${BASE_URL}/projects/${projectId}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok || !res.body) {
      let detail = res.statusText;
      try {
        detail = (await res.json()).detail ?? detail;
      } catch {
        // response wasn't JSON; fall back to statusText
      }
      throw new ApiError(res.status, detail);
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? "";
      for (const frame of frames) {
        if (!frame.startsWith("data: ")) continue;
        onEvent(JSON.parse(frame.slice("data: ".length)) as ChatEvent);
      }
    }
  },

  /** GET-based SSE, so a native EventSource works directly — returns an
   * unsubscribe function. Fires `onEvent({type: "changed", ...})` whenever
   * anything (chat or a direct tab edit) mutates the project's plan. */
  subscribePlanEvents: (projectId: string, onEvent: (event: PlanEvent) => void): (() => void) => {
    const source = new EventSource(`${BASE_URL}/projects/${projectId}/plan-events`);
    source.onmessage = (ev) => {
      try {
        onEvent(JSON.parse(ev.data) as PlanEvent);
      } catch {
        // malformed frame; ignore
      }
    };
    return () => source.close();
  },

  // ---- excel (feature.md §9) --------------------------------------------------
  exportExcelUrl: (projectId: string) => `${BASE_URL}/projects/${projectId}/export.xlsx`,
  importExcel: async (projectId: string, file: File, confirm = false): Promise<Setup> => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(
      `${BASE_URL}${withConfirm(`/projects/${projectId}/import`, confirm)}`,
      { method: "POST", body: form },
    );
    if (!res.ok) {
      let detail = res.statusText;
      try {
        detail = (await res.json()).detail ?? detail;
      } catch {
        // response wasn't JSON; fall back to statusText
      }
      throw new ApiError(res.status, detail);
    }
    return (await res.json()) as Setup;
  },
};
