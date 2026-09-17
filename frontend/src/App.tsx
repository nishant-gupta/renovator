import { useEffect, useState } from "react";
import "./App.css";
import { api } from "./api/client";
import type { ProjectSummary } from "./api/types";
import { ChatPanel } from "./components/ChatPanel";
import { Rail, type TabId } from "./components/Rail";
import { TopBar } from "./components/TopBar";
import { ProjectsTab } from "./tabs/ProjectsTab";
import { SetupTab } from "./tabs/SetupTab";
import { TasksTab } from "./tabs/TasksTab";
import { ScheduleTab } from "./tabs/ScheduleTab";
import { MaterialsTab } from "./tabs/MaterialsTab";
import { EstimateTab } from "./tabs/EstimateTab";
import { TrackTab } from "./tabs/TrackTab";

const STORAGE_KEY = "renovator.projectId";

function pickActiveId(list: ProjectSummary[], current: string | null): string | null {
  if (current && list.some((p) => p.id === current)) return current;
  return list[0]?.id ?? null;
}

function App() {
  const [activeTab, setActiveTab] = useState<TabId>("projects");
  const [projects, setProjects] = useState<ProjectSummary[] | null>(null);
  const [projectId, setProjectId] = useState<string | null>(() => localStorage.getItem(STORAGE_KEY));
  const [loadError, setLoadError] = useState<string | null>(null);
  const [hasLlmKey, setHasLlmKey] = useState(false);
  // Bumped whenever the active project's plan changes (chat, or a direct
  // edit) — threaded into every tab's useFetch deps as the signal to
  // re-fetch (design doc §4.10's "the stream just tells it when to
  // re-fetch/re-render").
  const [planVersion, setPlanVersion] = useState(0);

  useEffect(() => {
    refreshProjects();
    api.getHealth().then((h) => setHasLlmKey(h.has_llm_key)).catch(() => setHasLlmKey(false));
  }, []);

  useEffect(() => {
    if (projectId) localStorage.setItem(STORAGE_KEY, projectId);
    else localStorage.removeItem(STORAGE_KEY);
  }, [projectId]);

  useEffect(() => {
    if (!projectId) return;
    // No need to reset planVersion per project — it's just a change
    // counter threaded into every tab's useFetch deps alongside
    // projectId, which already forces a refetch on its own when it
    // changes.
    const unsubscribe = api.subscribePlanEvents(projectId, (event) => {
      if (event.type === "changed") setPlanVersion((v) => v + 1);
    });
    return unsubscribe;
  }, [projectId]);

  function refreshProjects(nextActiveId?: string) {
    api
      .listProjects()
      .then((list) => {
        setProjects(list);
        setProjectId((current) => pickActiveId(list, nextActiveId ?? current));
      })
      .catch((e) => setLoadError(String(e)));
  }

  function openProject(id: string) {
    setProjectId(id);
    setActiveTab("tasks");
  }

  if (loadError) return <div className="empty empty-error">Couldn't load projects: {loadError}</div>;
  if (!projects) return <div className="empty">Loading…</div>;

  // Nothing to show anywhere else until a project exists — the Projects
  // tab (create/select) is the only usable surface at that point.
  const effectiveTab = projectId ? activeTab : "projects";
  const currentProject = projects.find((p) => p.id === projectId) ?? null;

  return (
    <div className="app">
      <Rail activeTab={effectiveTab} onTabChange={setActiveTab} projectId={projectId} />
      <main className="main">
        {effectiveTab !== "projects" && (
          <TopBar project={currentProject} onSwitch={() => setActiveTab("projects")} />
        )}
        {effectiveTab === "projects" && (
          <ProjectsTab
            projects={projects}
            activeProjectId={projectId}
            onOpen={openProject}
            onProjectsChanged={refreshProjects}
          />
        )}
        {projectId && effectiveTab === "setup" && <SetupTab projectId={projectId} planVersion={planVersion} />}
        {projectId && effectiveTab === "tasks" && <TasksTab projectId={projectId} planVersion={planVersion} />}
        {projectId && effectiveTab === "schedule" && (
          <ScheduleTab projectId={projectId} planVersion={planVersion} />
        )}
        {projectId && effectiveTab === "materials" && (
          <MaterialsTab projectId={projectId} planVersion={planVersion} />
        )}
        {projectId && effectiveTab === "estimate" && (
          <EstimateTab projectId={projectId} planVersion={planVersion} />
        )}
        {projectId && effectiveTab === "track" && <TrackTab projectId={projectId} planVersion={planVersion} />}
      </main>
      {projectId && <ChatPanel key={projectId} projectId={projectId} hasLlmKey={hasLlmKey} />}
    </div>
  );
}

export default App;
