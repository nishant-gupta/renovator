import { useRef, useState } from "react";
import { api, ApiError } from "../api/client";

export type TabId = "projects" | "setup" | "tasks" | "schedule" | "materials" | "estimate" | "track";

const TABS: { id: TabId; label: string; icon: string }[] = [
  { id: "projects", label: "Projects", icon: "▣" },
  { id: "setup", label: "Setup", icon: "⚙" },
  { id: "tasks", label: "Tasks", icon: "▤" },
  { id: "schedule", label: "Schedule", icon: "▦" },
  { id: "materials", label: "Materials", icon: "▩" },
  { id: "estimate", label: "Estimate", icon: "₹" },
  { id: "track", label: "Track", icon: "◉" },
];

interface RailProps {
  activeTab: TabId;
  onTabChange: (tab: TabId) => void;
  projectId: string | null;
}

export function Rail({ activeTab, onTabChange, projectId }: RailProps) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);

  function handleExport() {
    if (!projectId) return;
    const a = document.createElement("a");
    a.href = api.exportExcelUrl(projectId);
    a.click();
  }

  async function handleImportFile(file: File) {
    if (!projectId) return;
    setImportError(null);
    setImporting(true);
    try {
      await api.importExcel(projectId, file);
    } catch (e) {
      if (e instanceof ApiError && e.needsConfirmation) {
        if (window.confirm(e.detail)) {
          try {
            await api.importExcel(projectId, file, true);
          } catch (e2) {
            setImportError(e2 instanceof ApiError ? e2.detail : String(e2));
            setImporting(false);
            return;
          }
        } else {
          setImporting(false);
          return;
        }
      } else {
        setImportError(e instanceof ApiError ? e.detail : String(e));
        setImporting(false);
        return;
      }
    }
    // Import replaces the whole plan — every tab's fetched state is stale,
    // and there's no cross-tab live-update channel yet (that's Phase 7's
    // SSE work), so a full reload is the simplest correct way to reflect it.
    window.location.reload();
  }

  return (
    <nav className="rail">
      <div className="rail-brand">
        <span className="rail-brand-mark" />
        <div className="rail-brand-name">
          Renovator
          <span>local planner</span>
        </div>
      </div>
      <div className="rail-nav">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            className={`rail-navbtn ${activeTab === tab.id ? "active" : ""}`}
            onClick={() => onTabChange(tab.id)}
          >
            <span className="rail-ic">{tab.icon}</span>
            {tab.label}
          </button>
        ))}
      </div>
      <div className="rail-foot">
        {importError && <div className="rail-error">{importError}</div>}
        <button className="rail-act" disabled={!projectId} onClick={handleExport}>
          ↧ Export Excel
        </button>
        <button className="rail-act" disabled={!projectId || importing} onClick={() => fileInput.current?.click()}>
          {importing ? "Importing…" : "↥ Import Excel"}
        </button>
        <input
          ref={fileInput}
          type="file"
          accept=".xlsx,.xls"
          style={{ display: "none" }}
          onChange={(e) => {
            const file = e.target.files?.[0];
            e.target.value = "";
            if (file) handleImportFile(file);
          }}
        />
        <div className="rail-note">Local · agent chat not wired up yet</div>
      </div>
    </nav>
  );
}
