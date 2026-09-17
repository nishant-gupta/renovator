// Indian Rupees with Indian digit grouping (feature.md §12).
const inr = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });

export function money(n: number | null | undefined): string {
  return `₹${inr.format(Math.round(n ?? 0))}`;
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(`${iso}T12:00:00`);
  return d.toLocaleDateString("en-US", { day: "numeric", month: "short" });
}
