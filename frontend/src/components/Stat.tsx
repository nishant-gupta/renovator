import type { ReactNode } from "react";

interface StatProps {
  label: string;
  value: string;
  note?: string;
  tone?: "default" | "danger" | "ok";
}

export function Stat({ label, value, note, tone = "default" }: StatProps) {
  return (
    <div className="stat">
      <div className="stat-label">{label}</div>
      <div className={`stat-value stat-value-${tone}`}>{value}</div>
      {note && <div className="stat-note">{note}</div>}
    </div>
  );
}

export function StatRow({ children }: { children: ReactNode }) {
  return <div className="stat-row">{children}</div>;
}
