// Local-date helpers for the Schedule views. Dates are kept at noon local
// time (matching the backend's date-only, not datetime, semantics) so
// adding/subtracting days never trips over a DST boundary.

export function parseISO(s: string): Date {
  const [y, m, d] = s.split("-").map(Number);
  const date = new Date(y, m - 1, d);
  date.setHours(12, 0, 0, 0);
  return date;
}

export function isoDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function addDays(d: Date, n: number): Date {
  const x = new Date(d);
  x.setDate(x.getDate() + n);
  x.setHours(12, 0, 0, 0);
  return x;
}

export function daysDiff(a: Date, b: Date): number {
  return Math.round((b.getTime() - a.getTime()) / 86_400_000);
}

export function isWeekend(d: Date): boolean {
  const g = d.getDay();
  return g === 0 || g === 6;
}

export type WeekendPolicy = "none" | "saturdays" | "all";

/** Mirrors the backend's is_workday (engine/schedule.py) — a day off under
 * the project's weekend_policy, or an explicitly blocked_dates entry. */
export function isWorkday(d: Date, weekendPolicy: WeekendPolicy, blockedDates: ReadonlySet<string> = new Set()): boolean {
  if (blockedDates.has(isoDate(d))) return false;
  const day = d.getDay(); // 0=Sun ... 6=Sat
  if (weekendPolicy === "all") return true;
  if (weekendPolicy === "saturdays") return day !== 0; // only Sunday is off
  return day !== 0 && day !== 6; // "none": both weekend days are off
}

export function fmtDayLabel(d: Date): string {
  return `${d.getDate()} ${d.toLocaleString("en-US", { month: "short" })}`;
}

export function weekdayShort(d: Date): string {
  return d.toLocaleString("en-US", { weekday: "short" });
}

/** Monday of the week containing `d`. */
export function isoWeekStart(d: Date): Date {
  const dow = (d.getDay() + 6) % 7; // days since Monday
  return addDays(d, -dow);
}
