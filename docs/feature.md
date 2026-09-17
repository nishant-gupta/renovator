# Renovation Self-Planner — Full Feature & Interaction Guide

A complete reference for the planner in `Renovation_Planner_v2.html`. It covers the mental model the app is built on, every tab and control, the task editor, the scheduling engine, and how saving and Excel import/export behave.

The app is a single self-contained HTML file. It needs no server, no account, and no internet connection to run (the only external resource is the Excel library, used only when you actually import or export). Open it in any modern browser and it works.

---

## 1. The mental model

Five ideas underpin everything. Once these click, the whole app is predictable.

**Task.** A task is one unit of work — "Re-tile bathroom wall", "TV unit", "Fresh paint". It is what you see as a single row on the Tasks and Track tabs and a single bar on the schedule. Every task belongs to a room and a category, and carries a duration, a phase, an optional stage, a mandatory/optional flag, and any dependencies.

**Lines (single vs. split).** Under the hood a task is made of one or more *lines*. Most tasks are a single line. But many renovation jobs are naturally "material plus labour" — you buy tiles *and* pay a tiler. For those you can make a task a **split task**: one Material line and one Labour line that are created, edited, moved, and scheduled together as a single task, but costed separately. This is why the Materials tab can list the tiles while the Estimate still shows the job as one item. Split tasks show a "(Mat+Lab)" tag and expand to reveal their two lines.

**Rooms.** A flat list of areas ("Master Bedroom", "Kids Bathroom", "Overall (Whole House)"). Every task lives in exactly one room. Rooms are managed centrally in Setup.

**Rate card.** A single shared price list — "Tile — material ₹130/sqft", "Painter labour ₹9/sqft", and so on. A task can be costed either by picking a rate and entering a quantity (rate × qty) or by typing a flat/quoted amount. Because rates live in one place, correcting a price once re-costs every task that uses it. This is the "common rates managed in one place" requirement.

**Phases vs. stages — two independent axes.** These are easy to confuse, so hold them apart:

- A **phase** answers *"are we doing this now, or later?"* — it is your budget/priority bucket (Phase 1 — Now, Phase 2 — Next, Phase 3 — Later). Phases drive the filter chips that appear across most tabs.
- A **stage** answers *"in what trade order does this happen on site?"* — Civil & POP → Rough plumbing → Rough electrical → False ceiling → Tiling → Glasswork → Painting → Electrical fixtures → Bathroom fixtures → Carpentry. Stages drive the *sequence* of the schedule.

A task can be Phase 1 (do it soon) and Stage "Painting" (happens mid-sequence on site) at the same time. The two never fight.

**Dependencies.** A line can depend on other lines that must *finish* before it can start ("paint" depends on "wall repair"). Dependencies are enforced when computing schedule dates, and the app blocks you from creating a circular chain.

**Duration.** Each task has a length in **working days**. This, plus the start date, stage order, and dependencies, is what lets the app place real calendar dates on everything.

---

## 2. The workspace

The left rail is always visible and holds:

- **Six tab buttons** — Setup, Tasks, Schedule, Materials, Estimate, Track. Click to switch; the active tab is highlighted.
- **Project start date** — a date picker. Changing it re-flows the entire schedule from that day.
- **↧ Export Excel** — downloads your whole plan as a `.xlsx` workbook.
- **↥ Import Excel** — opens a file picker to load a plan back in from a workbook.
- **↺ Reset to example** — after a confirmation, wipes your data and restores the built-in example plan.
- **A save indicator** — shows "Saving…", then "Saved 14:32" (or "Saved in browser 14:32"), so you always know your work is stored.

### How saving works

The app saves automatically a fraction of a second after any change — you never press a save button. It writes to persistent storage where available, and falls back to your browser's local storage otherwise. If neither is available (for example, some locked-down environments), the save note reminds you to use **Export** to keep your work. Excel export is therefore both a sharing format *and* your reliable long-term backup.

---

## 3. Setup tab — the "common place"

This is where you configure the building blocks every other tab reuses. It is divided into cards.

**Project timing.** Set the **project start date** and tick **Work on weekends too** if your crew works seven days a week. When weekends are off, the scheduler skips Saturdays and Sundays when counting working days; when on, it counts every day.

**Rooms / areas.** A table of every room with a count of how many tasks use it.
- Edit a room's name inline — renaming it updates every task in that room automatically.
- **✕** removes a room, but only if no task uses it (the app tells you how many tasks block the deletion).
- **+ Add room** prompts for a new area name.

**Rate card — the common place for prices.** A table of every rate: its label, unit, price per unit, and how many tasks use it.
- Edit any price inline in the ₹ field; every task costed by that rate instantly re-costs across the app.
- **✕** deletes a rate (with a warning if tasks currently use it — those tasks fall to zero cost until you fix them).
- **+ Add rate** prompts for a name, unit, and price.

**Phases — now / next / later.** A table of your phase buckets.
- Reorder with the **▲ / ▼** arrows (order defines "sooner vs. later").
- Rename inline.
- **✕** removes a phase; any tasks in it move to a remaining phase (you're warned first). You must always keep at least one phase.
- **+ Add phase** for extra buckets ("Someday", "Phase 4").

**Stages — trade execution order.** A numbered table where the number *is* the on-site sequence.
- Reorder with **▲ / ▼** — this directly changes the order trades run in the schedule.
- Rename inline.
- **✕** removes a stage; tasks in it become "unassigned" (schedulable but with no forced position).
- **+ Add stage** for trades not in the default list (e.g. "Waterproofing").

---

## 4. Tasks tab — building the plan

This is the working list of everything to be done.

**Room filter chips.** A row of chips — "All" plus one per room. Click to narrow the table to a single room. The active chip is highlighted.

**Phase filter chips.** A second row filters by phase ("All", "Phase 1 — Now", …), shared with the other tabs.

**Search.** A search box filters the visible tasks by name, room, or category.

**The task table.** Columns: Room, Task (with a trade-colour dot and, for split tasks, a "Mat+Lab" tag), Type, Qty, Days (duration), Cost, and a mandatory/optional flag. Interactions:
- Click the **▸ / ▾ chevron** on a split task to expand it and see its Material and Labour lines separately.
- Click a **row** (or the edit affordance) to open the task editor.
- A **checkbox** on each row adds it to a multi-select.

**Adding work — two ways:**
- **+ Add task** opens a blank task editor.
- **+ From template** opens the template picker (see §4.2), which prefills a common job for you.

**+ Add room** is also available here as a shortcut when you realise mid-planning you need a new area.

### 4.1 The task editor (modal)

Opened by adding or editing a task. It is a single focused form:

- **Room / Area** and **Category** dropdowns. Changing the category auto-fills a sensible trade and a default duration for that kind of work (you can override both).
- **Task name** — free text; the field is focused automatically on a new task so you can just start typing.
- **Structure** — a choice between **Single line** and **Material + Labour (together)**. Switching to split reveals two sub-sections; switching back collapses to one.
- **Stage** dropdown — pick a stage, choose "— No stage —", or **"+ New stage…"** to create one on the spot without leaving the form.
- **Phase** dropdown.
- **Flag** — Mandatory or Optional.
- **Duration (working days)** — a number field.
- **Fixed start date (optional)** — a date picker. Leave it blank to let the app auto-schedule the task from its stage and dependencies; set it to pin the task to a specific start (useful for "the plumber can only come on the 10th").

For each line (single, or material and labour), you also set:
- **Worker / Trade** text.
- **Status** (Not Started / In Progress / On Hold / Done).
- **Costing method** — *Rate card × quantity* (pick a rate, enter quantity) or *Flat / quoted amount* (type a number).
- **Procurement status** (Material lines only) — To buy / Ordered / Delivered.
- **Depends on** — a checklist of every other task line; tick the ones that must finish first. (Material lines don't show this; the labour side carries the dependency in a split task.)
- **Actual cost** and **Notes** — optional.

A **live cost preview** at the bottom updates as you change rates, quantities, or amounts. **Save** commits; **Cancel** or the ✕ discards. On an existing task a **Delete** button is available. Keyboard shortcuts: **Enter** saves (except inside a notes field), **Esc** closes. If you try to save a dependency that would create a loop, the app refuses and tells you which line is the problem.

### 4.2 The template picker

**+ From template** opens a grid of ten common renovation jobs — Fresh paint, Re-tile wall/floor, Wall repair + POP, Flooring, Electrical points/fixtures, Countertop (granite), Glass shower partition, TV/storage unit, Skirting, and Custom purchase/fixture. Each card shows the job's trade colour, category, and whether it's a split (material + labour) or single job.

Picking a card opens the task editor already filled in with the right category, trade, structure, and a starting rate — you just set the room, name, quantity, and dates. A **Start blank instead** option is there if you'd rather not use a template.

### 4.3 Multi-select (bulk actions)

Ticking one or more task checkboxes reveals a bulk action bar showing the count selected, with:
- **Mark mandatory / Mark optional** — flag many tasks at once.
- **Move to phase…** — reassign the selection's phase.
- **Move to stage…** — reassign the selection's stage.
- **Delete** — remove all selected tasks (also cleans them out of other tasks' dependency lists).
- **✕ Clear** — deselect.

This makes re-planning fast — e.g. select everything optional and push it to Phase 3, or select all "Painting" work and drop it into the Painting stage.

---

## 5. Schedule tab — real dates

The heart of the rebuild. A segmented control switches between three views of the *same* computed schedule, and two checkboxes control how dates are calculated:

- **Run stages in order** — when on, each stage waits for the previous stage's work to finish before starting (the natural trade cascade: you don't paint before the plumbing is roughed in). Turn it off to let stages overlap and see the most compressed possible timeline.
- **Work weekends** — same setting as in Setup, mirrored here for convenience.

The project span (start date → computed end date) is shown so you can see the total length at a glance. A **trade colour legend** ties every view together — the same colour means the same trade on the timeline, the agenda, the board, and the estimate.

### 5.1 Timeline (Gantt)

A classic Gantt chart:
- A month-and-day header runs across the top, with **weekends shaded** and a **"today" line** marked.
- Rows are grouped by stage, in stage order.
- Each task is a **colour-coded bar** positioned on its computed start date and sized to its duration. Tasks with a fixed start date are flagged as such in the bar's tooltip.
- **Click any bar** to open that task's editor.
- The chart scrolls horizontally for long projects.

### 5.2 By date (agenda)

A day-planner view answering "what's happening, and who do I need, on each day":
- Grouped by week, then by day.
- Each task shows a **STARTS** badge on its first day and a "day n of N" indicator on subsequent days, so you can see multi-day jobs in progress.
- Every day lists the **trades needed that day** as coloured badges — your at-a-glance "call the electrician on Tuesday" view.

### 5.3 Board (drag & drop)

A kanban-style planner for arranging work by stage:
- One column per stage, each holding its task cards; cards carry a coloured left border by trade.
- **Drag a card** into another stage's column to reassign its stage.
- **Drag a stage's header** to reorder the stages themselves.
- **+ Add item here** at the bottom of a column opens a new task pre-set to that stage.
- A toggle reveals a **suggested execution order** — a dependency-aware, stage-ordered list of the whole plan (dependencies first, stage order breaking ties), useful as a sanity check on your sequencing.

---

## 6. Materials tab — procurement

Everything you need to buy, organised by *when* you'll need it on site.

- Each Material line becomes a row: the date it's **needed by** (derived from its task's scheduled start), the material name, room, quantity and unit, estimated cost, a **buy-status** selector, and a **vendor / note** field.
- Rows are **grouped by the week they're needed** ("Buy for week of 12 Oct…"), with a subtotal per group, and sorted earliest-first. **Overdue** need-by dates show in red.
- Four summary stats sit at the top: **material budget** (total), **still to buy** (value and count), **ordered** (count), and **delivered** (count).
- Change any row's status between **To buy → Ordered → Delivered** as you go; the colour and the top stats update.
- Type a **vendor or note** per material (this shares the line's note field, so it also shows on the task).
- A search box and the phase filter narrow the list.

Because need-by dates come from the live schedule, changing your start date or resequencing stages automatically re-sorts your shopping into the right weeks.

---

## 7. Estimate tab — the money view

A read-oriented breakdown of cost:
- Four stats: **grand total**, **mandatory** subtotal, **optional** subtotal, and **materials** subtotal — so you can instantly see how much is committed vs. nice-to-have, and how much is materials vs. labour.
- Three bar charts break the total down **by room**, **by trade** (colour-matched to the rest of the app), and **by phase**.
- A full task table sorted by cost, highest first, so the big-ticket items surface.

Everything here is derived live from your tasks and the rate card — there's nothing to edit on this tab; fix costs at the source (a task, or a rate in Setup) and this updates.

---

## 8. Track tab — during the build

The execution counterpart to the Estimate. As work actually happens:
- Log each task's **status** (Not Started / In Progress / On Hold / Done). Split tasks show a combined status; expand to set each line.
- Enter **actual cost** against the estimate.
- Add **notes**.
- Four stats track the build: **progress %** (lines done), **estimated total**, **actual so far**, and **variance** (actual − estimate, coloured red when you're over).

The variance figure only appears once you've logged at least one actual, so it stays meaningful.

---

## 9. Data, saving, and Excel

### Automatic saving

Covered in §2: changes save on their own, to persistent storage with a browser-storage fallback, with a visible save note. No manual save step exists or is needed.

### Export

**↧ Export Excel** produces a multi-sheet `.xlsx` workbook:
- **Project** — your start date and the weekend/stage-cascade settings.
- **Rate Card** — the full price list.
- **Phases** and **Stages** — the master lists, in order (so even empty phases/stages survive a round-trip).
- **Rooms & Items** — every task line with its category, trade, costing, cost, stage, phase, duration, fixed start, procurement status, dependencies, status, actuals, notes, and a stable Task ID.
- **Schedule** — every line with its **computed start and end dates**, stage, phase, room, trade, duration, and dependencies.
- **Materials** — the shopping list with need-by dates, quantities, costs, buy-status, and vendor notes.
- **Suggested Order** — the dependency-aware execution order.
- **Estimate Summary** — totals and the by-room / by-trade / by-phase breakdowns.
- **Track** — a compact status-and-actuals sheet.

This is your backup, your shareable plan, and something you can hand to a contractor.

### Import

**↥ Import Excel** reads a workbook back in, **replacing** the current plan (you're warned, and prompted to export first if you want to keep what you have). It re-links rates, rooms, phases, stages, dependencies, durations, fixed starts, and procurement statuses, and re-pairs any split material+labour tasks. A full export → re-import preserves everything, including empty phases.

**Backward compatibility.** It also reads plans exported from the *earlier* version of this planner. Older files stored the trade sequence differently (a combined phase label plus a separate "trade batch" column and no explicit stage or duration columns). On import the app detects this, rebuilds your stages from the old trade batches, resets phases to Now / Next / Later using each task's mandatory flag, and back-fills sensible default durations — then tells you it did so. You may end up with a few near-duplicate stages from the old two-axis format; merge or delete them in a few seconds on the Setup tab.

---

## 10. How the schedule is computed

For the curious, the dates come from a forward pass over your plan:

1. Everything starts no earlier than the **project start date**.
2. If **Run stages in order** is on, each stage can't start until every task in earlier stages has finished — the trade cascade.
3. A task also can't start until all the tasks it **depends on** have finished.
4. A task with a **fixed start date** is pinned there (still respecting working days).
5. From each task's start, its **duration in working days** is counted out — skipping weekends unless **Work weekends** is on — to find its end date.
6. The latest end date across the plan is the **project end**.

The result is memoised for speed and recomputed whenever anything that could affect dates changes — a task, a duration, the start date, stage order, or the two schedule toggles.

---

## 11. Suggested workflows

**Starting a real plan from the example.** Skim the example to see how things fit together, then either edit its tasks room by room, or hit **Reset to example** once you're ready and build fresh. Set your real project start date first so dates are meaningful as you go.

**Fastest way to enter a lot of work.** Use **+ From template** for the common jobs (paint, tile, POP, electrical) — it fills in trade, structure, and rate so you only add the room, quantity, and dates. Use bulk-select afterwards to flag optionals and drop things into phases and stages in batches.

**Getting the sequence right.** Assign stages as you enter tasks (or drag cards on the Board later). Keep **Run stages in order** on for a realistic timeline; turn it off briefly to see the theoretical fastest finish. Add dependencies only where one specific job truly blocks another (leak fix before re-tiling, wall repair before paint) — the stage cascade already handles the broad trade order, so you don't need to wire up every relationship by hand.

**Managing the budget.** Watch the Estimate tab's mandatory-vs-optional split. If you're over, select optional tasks and push them to a later phase rather than deleting them — they stay in the plan for "someday".

**On site.** Live in the Materials and Track tabs: order materials by their need-by week, mark them delivered, and log status and actuals as work completes so variance stays honest.

---

## 12. Notes and limits

- The app is offline-first; the only network use is loading the Excel library, and only when you import or export.
- Everything is one file — to move your setup to another computer, either copy the HTML (it carries no data) and import your exported workbook, or just work from the workbook.
- There is no multi-user or real-time collaboration; share by exporting the workbook.
- Costs are shown in Indian Rupees (₹) with Indian digit grouping.