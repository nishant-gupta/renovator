import { useEffect, useRef, useState } from "react";

interface MenuItem {
  label: string;
  onSelect: () => void;
}

interface MenuProps {
  label: string;
  items: MenuItem[];
  tone?: "default" | "danger";
  /** "icon" trims the trigger to a compact icon-btn with no caret, for
   * tight table-row contexts (e.g. a phase row's transfer action). */
  variant?: "button" | "icon";
  title?: string;
}

/** A button that opens a small anchored list of actions — the "Move to
 * phase…"/"Move to stage…" pattern, without the confusing semantics of a
 * native <select> that fires on change and has to reset itself afterward. */
export function Menu({ label, items, tone = "default", variant = "button", title }: MenuProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onDocMouseDown(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDocMouseDown);
    return () => document.removeEventListener("mousedown", onDocMouseDown);
  }, [open]);

  return (
    <div className="menu" ref={ref}>
      <button
        type="button"
        className={
          variant === "icon"
            ? "icon-btn menu-trigger-icon"
            : `btn-ghost menu-trigger ${tone === "danger" ? "menu-trigger-danger" : ""}`
        }
        title={title}
        onClick={() => setOpen((o) => !o)}
      >
        {label}
        {variant === "button" && <span className="menu-caret">▾</span>}
      </button>
      {open && (
        <div className="menu-list">
          {items.length === 0 && <div className="menu-empty">Nothing to pick</div>}
          {items.map((item) => (
            <button
              type="button"
              key={item.label}
              className="menu-item"
              onClick={() => {
                setOpen(false);
                item.onSelect();
              }}
            >
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
