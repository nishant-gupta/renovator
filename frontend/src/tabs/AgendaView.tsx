import { addDays, fmtDayLabel, isWeekend, isWorkday, isoDate, isoWeekStart, parseISO, weekdayShort } from "../dates";
import { tradeBucket, tradeColorVar } from "../trade";
import type { ScheduledTaskView } from "../api/types";
import type { WeekendPolicy } from "../dates";

interface AgendaViewProps {
  tasks: ScheduledTaskView[];
  weekendPolicy: WeekendPolicy;
  blockedDates: string[];
  onOpenTask: (taskId: string) => void;
}

interface DayRow {
  date: Date;
  starting: ScheduledTaskView[];
  active: ScheduledTaskView[];
}

export function AgendaView({ tasks, weekendPolicy, blockedDates, onOpenTask }: AgendaViewProps) {
  const shown = tasks.filter((t) => t.start && t.end);
  if (shown.length === 0) return <div className="empty">No scheduled tasks match.</div>;
  const blockedSet = new Set(blockedDates);

  let minD = parseISO(shown[0].start!);
  let maxD = parseISO(shown[0].end!);
  for (const t of shown) {
    const s = parseISO(t.start!);
    const e = parseISO(t.end!);
    if (s < minD) minD = s;
    if (e > maxD) maxD = e;
  }

  const rowsByDate = new Map<string, DayRow>();
  for (let d = new Date(minD); d <= maxD; d = addDays(d, 1)) {
    if (!isWorkday(d, weekendPolicy, blockedSet)) continue;
    const key = isoDate(d);
    const starting = shown.filter((t) => t.start === key);
    const active = shown.filter((t) => t.start! <= key && key <= t.end!);
    if (!active.length) continue;
    rowsByDate.set(key, { date: new Date(d), starting, active });
  }

  const weeks = new Map<string, string[]>();
  for (const key of rowsByDate.keys()) {
    const wk = isoDate(isoWeekStart(rowsByDate.get(key)!.date));
    const list = weeks.get(wk) ?? [];
    list.push(key);
    weeks.set(wk, list);
  }
  const weekKeys = [...weeks.keys()].sort();

  return (
    <>
      {weekKeys.map((wk) => {
        const dayKeys = weeks.get(wk)!.sort();
        const wkEnd = addDays(parseISO(wk), 6);
        return (
          <div className="agwk" key={wk}>
            <div className="agwk-h">
              Week of {fmtDayLabel(parseISO(wk))} — {fmtDayLabel(wkEnd)}
            </div>
            {dayKeys.map((dk) => {
              const row = rowsByDate.get(dk)!;
              const trades = [...new Set(row.active.map((t) => tradeBucket(t.worker_type || t.category).key))];
              const tradeNames = new Map(
                row.active.map((t) => {
                  const b = tradeBucket(t.worker_type || t.category);
                  return [b.key, b.name] as const;
                }),
              );
              return (
                <div className={`agday ${isWeekend(row.date) ? "we" : ""}`} key={dk}>
                  <div className="agday-date">
                    {row.date.getDate()} {row.date.toLocaleString("en-US", { month: "short" })}
                    <div className="wd">{weekdayShort(row.date)}</div>
                  </div>
                  <div className="agday-body">
                    {row.active.map((t) => {
                      const isStart = row.starting.includes(t);
                      const dayNum =
                        Math.round((parseISO(dk).getTime() - parseISO(t.start!).getTime()) / 86_400_000) + 1;
                      return (
                        <div className="agtask" key={t.task_id} onClick={() => onOpenTask(t.task_id)}>
                          <span
                            className="dot"
                            style={{ background: tradeColorVar(tradeBucket(t.worker_type || t.category).key) }}
                          />
                          <span>
                            {t.name} <span className="muted">· {t.room}</span>
                          </span>
                          {isStart ? (
                            <span className="start">STARTS</span>
                          ) : (
                            <span className="cont">
                              day {dayNum}/{t.duration_days}
                            </span>
                          )}
                        </div>
                      );
                    })}
                    <div className="agtrades">
                      {trades.map((key) => (
                        <span className="badge" key={key}>
                          <span className="dot" style={{ background: tradeColorVar(key) }} />
                          {tradeNames.get(key)}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        );
      })}
    </>
  );
}
