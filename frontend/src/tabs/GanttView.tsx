import type { ReactNode } from "react";
import { addDays, daysDiff, fmtDayLabel, isWeekend, isoDate, parseISO } from "../dates";
import { tradeBucket, tradeColorVar } from "../trade";
import type { ScheduledTaskView, Stage } from "../api/types";

const DAY_WIDTH = 30;

interface GanttViewProps {
  tasks: ScheduledTaskView[];
  stages: Stage[];
  onOpenTask: (taskId: string) => void;
}

export function GanttView({ tasks, stages, onOpenTask }: GanttViewProps) {
  const shown = tasks.filter((t) => t.start && t.end);
  if (shown.length === 0) return <div className="empty">No scheduled tasks match. Add tasks to see them here.</div>;

  let minD = parseISO(shown[0].start!);
  let maxD = parseISO(shown[0].end!);
  for (const t of shown) {
    const s = parseISO(t.start!);
    const e = parseISO(t.end!);
    if (s < minD) minD = s;
    if (e > maxD) maxD = e;
  }
  minD = addDays(minD, -1);
  maxD = addDays(maxD, 2);
  const totalDays = Math.max(1, daysDiff(minD, maxD) + 1);
  const today = new Date();
  today.setHours(12, 0, 0, 0);

  const days: Date[] = [];
  for (let i = 0; i < totalDays; i++) days.push(addDays(minD, i));

  const months: { key: string; label: string; n: number }[] = [];
  for (const d of days) {
    const key = `${d.getFullYear()}-${d.getMonth()}`;
    const last = months[months.length - 1];
    if (last && last.key === key) {
      last.n++;
    } else {
      months.push({ key, label: d.toLocaleString("en-US", { month: "long", year: "numeric" }), n: 1 });
    }
  }

  function overlays() {
    const nodes: ReactNode[] = [];
    days.forEach((d, i) => {
      if (isWeekend(d)) {
        nodes.push(
          <div key={`we-${i}`} className="g-weekend" style={{ left: i * DAY_WIDTH, width: DAY_WIDTH }} />,
        );
      }
    });
    const ti = daysDiff(minD, today);
    if (ti >= 0 && ti < totalDays) {
      nodes.push(<div key="today" className="g-todayline" style={{ left: ti * DAY_WIDTH + DAY_WIDTH / 2 }} />);
    }
    return nodes;
  }

  const stagesInOrder = stages;
  const groups: { label: string; tasks: ScheduledTaskView[] }[] = [];
  for (const stage of stagesInOrder) {
    const ts = shown.filter((t) => t.stage_id === stage.id);
    if (ts.length) groups.push({ label: stage.label, tasks: ts });
  }
  const stageIds = new Set(stages.map((s) => s.id));
  const unassigned = shown.filter((t) => t.stage_id == null || !stageIds.has(t.stage_id));
  if (unassigned.length) groups.push({ label: "Unassigned", tasks: unassigned });

  return (
    <div className="gantt-wrap">
      <div className="gantt" style={{ minWidth: 200 + totalDays * DAY_WIDTH }}>
        <div className="g-head">
          <div className="g-lbl-col">Task</div>
          <div>
            <div className="g-months">
              {months.map((m) => (
                <div key={m.key} className="g-month" style={{ width: m.n * DAY_WIDTH }}>
                  {m.label}
                </div>
              ))}
            </div>
            <div className="g-days">
              {days.map((d, i) => (
                <div
                  key={i}
                  className={`g-day ${isWeekend(d) ? "we" : ""} ${isoDate(d) === isoDate(today) ? "today" : ""}`}
                  style={{ width: DAY_WIDTH }}
                >
                  {d.getDate()}
                </div>
              ))}
            </div>
          </div>
        </div>
        <div className="g-body">
          {groups.map((g) => (
            <div key={g.label}>
              <div className="g-stagehdr">
                <div className="g-lbl-col">{g.label}</div>
                <div className="g-grid" style={{ width: totalDays * DAY_WIDTH }}>
                  {overlays()}
                </div>
              </div>
              {g.tasks.map((t) => {
                const start = parseISO(t.start!);
                const end = parseISO(t.end!);
                const off = daysDiff(minD, start);
                const span = daysDiff(start, end) + 1;
                const color = tradeColorVar(tradeBucket(t.worker_type || t.category).key);
                const title = `${t.name} · ${fmtDayLabel(start)}–${fmtDayLabel(end)} · ${t.duration_days}d${
                  t.fixed_start ? " · fixed start" : ""
                }`;
                return (
                  <div key={t.task_id} className="g-taskrow">
                    <div className="g-tasklbl" onClick={() => onOpenTask(t.task_id)} title={`${t.room} — ${t.name}`}>
                      <span className="dot" style={{ background: color }} />
                      <span className="nm">
                        {t.name} <span className="rm">· {t.room}</span>
                      </span>
                    </div>
                    <div className="g-lane" style={{ width: totalDays * DAY_WIDTH }}>
                      {overlays()}
                      <div
                        className="g-bar"
                        style={{
                          left: off * DAY_WIDTH + 2,
                          width: span * DAY_WIDTH - 4,
                          background: color,
                        }}
                        onClick={() => onOpenTask(t.task_id)}
                        title={title}
                      >
                        <span className="barlbl">{t.name}</span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
