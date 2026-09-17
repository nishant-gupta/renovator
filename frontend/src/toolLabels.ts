// Human labels for the tool names the backend can report in a chat turn
// (backend/src/renovator/agents/tool_bindings.py). Keeps the chat dock's
// tool-call/result lines to one short phrase instead of the raw name; an
// unlisted tool just falls back to its name with underscores turned into
// spaces, so a new tool never breaks this — it's just less polished until
// someone adds a proper label.
const TOOL_LABELS: Record<string, string> = {
  get_setup: "Checked setup",
  get_tasks: "Checked tasks",
  get_schedule: "Checked schedule",
  get_suggested_order: "Checked suggested order",
  get_materials_plan: "Checked materials plan",
  get_estimate_summary: "Checked cost estimate",
  get_track_summary: "Checked progress",
  list_templates: "Checked templates",
  get_changelog: "Checked change history",
  add_room: "Added a room",
  rename_room: "Renamed a room",
  remove_room: "Removed a room",
  add_rate: "Added a rate",
  update_rate: "Updated a rate",
  delete_rate: "Deleted a rate",
  add_phase: "Added a phase",
  rename_phase: "Renamed a phase",
  remove_phase: "Removed a phase",
  move_phase: "Reordered phases",
  add_stage: "Added a stage",
  rename_stage: "Renamed a stage",
  remove_stage: "Removed a stage",
  move_stage: "Reordered stages",
  set_project_settings: "Updated project settings",
  instantiate_template: "Created a task from a template",
  create_task: "Created a task",
  update_task: "Updated a task",
  delete_task: "Deleted a task",
  set_dependencies: "Updated dependencies",
  bulk_set_mandatory: "Updated tasks",
  bulk_move_to_phase: "Moved tasks to a phase",
  bulk_move_to_stage: "Moved tasks to a stage",
  bulk_delete_tasks: "Deleted tasks",
  export_plan_to_excel: "Exported to Excel",
  import_plan_from_excel: "Imported from Excel",
  search_material_rate: "Searched material rates",
  search_vendors: "Searched vendors",
  task: "Delegated to a sub-agent",
};

export function toolLabel(name: string): string {
  return TOOL_LABELS[name] ?? name.replace(/_/g, " ");
}
