import type { ProjectSummary } from "../api/types";

interface TopBarProps {
  project: ProjectSummary | null;
  onSwitch: () => void;
}

/** Read-only project context shown above every tab except Projects itself
 * — switching projects only happens from the Projects tab now. */
export function TopBar({ project, onSwitch }: TopBarProps) {
  return (
    <div className="topbar">
      <span className="topbar-kicker">Project</span>
      <span className="topbar-name">{project?.name ?? "No project selected"}</span>
      <button className="topbar-switch" onClick={onSwitch}>
        Switch project
      </button>
    </div>
  );
}
