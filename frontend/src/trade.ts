// Port of tradeBucket()/tradeColor() (Renovation_Planner_v2.html:322-337) —
// classifies a worker_type/category string into a trade bucket so the
// Gantt/agenda/board views all colour the same trade consistently.

export interface TradeBucket {
  key: string;
  name: string;
}

const TRADE_BUCKETS: { test: RegExp; key: string; name: string }[] = [
  { test: /glass/i, key: "glass", name: "Glass" },
  { test: /plumb/i, key: "plumber", name: "Plumber" },
  { test: /electr/i, key: "electric", name: "Electrician" },
  { test: /tile|tiling/i, key: "tiling", name: "Tiling" },
  { test: /paint/i, key: "painter", name: "Painter" },
  { test: /carpenter|carpentry|furnish|vendor/i, key: "carpenter", name: "Carpenter" },
  { test: /mason|civil|pop|floor/i, key: "mason", name: "Mason / Civil" },
  { test: /material/i, key: "material", name: "Material" },
];

export function tradeBucket(text: string | null | undefined): TradeBucket {
  const s = text ?? "";
  for (const b of TRADE_BUCKETS) {
    if (b.test.test(s)) return { key: b.key, name: b.name };
  }
  return { key: "other", name: s.trim() || "Other" };
}

export function tradeColorVar(key: string): string {
  return `var(--t-${key}, var(--t-other))`;
}
