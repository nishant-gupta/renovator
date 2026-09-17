import { api, ApiError } from "../api/client";
import { useFetch } from "../api/hooks";
import { StatRow, Stat } from "../components/Stat";
import { fmtDate, money } from "../format";
import type { BuyStatus } from "../api/types";

const BUY_STATUSES: BuyStatus[] = ["To buy", "Ordered", "Delivered"];

export function MaterialsTab({ projectId, planVersion }: { projectId: string; planVersion: number }) {
  const { data: materials, error, loading, reload } = useFetch(
    () => api.getMaterials(projectId),
    [projectId, planVersion],
  );

  async function setBuyStatus(lineId: string, buy_status: BuyStatus) {
    try {
      await api.updateLine(projectId, lineId, { buy_status });
      reload();
    } catch (e) {
      window.alert(e instanceof ApiError ? e.detail : String(e));
    }
  }

  async function setNotes(lineId: string, notes: string) {
    try {
      await api.updateLine(projectId, lineId, { notes });
      reload();
    } catch (e) {
      window.alert(e instanceof ApiError ? e.detail : String(e));
    }
  }

  if (loading) return <div className="empty">Loading…</div>;
  if (error) return <div className="empty empty-error">Couldn't load materials: {error}</div>;
  if (!materials) return null;

  return (
    <div>
      <h1 className="page-h">Materials</h1>
      <p className="page-sub">Everything you need to buy, grouped by when it's needed on site.</p>

      <StatRow>
        <Stat label="Material budget" value={money(materials.total)} />
        <Stat label="Still to buy" value={money(materials.to_buy_cost)} note={`${materials.to_buy_count} items`} />
        <Stat label="Ordered" value={String(materials.ordered_count)} />
        <Stat label="Delivered" value={String(materials.delivered_count)} />
      </StatRow>

      {materials.groups.length === 0 && <div className="empty">No material lines yet.</div>}
      {materials.groups.map((group) => (
        <table className="dt dt-grouped" key={group.week_key}>
          <thead>
            <tr>
              <th colSpan={7} className="grp-header">
                {group.week_key === "zzz" ? "No scheduled date" : `Buy for week of ${fmtDate(group.week_key)}`} ·{" "}
                {money(group.subtotal)}
              </th>
            </tr>
            <tr>
              <th>Need by</th>
              <th>Material</th>
              <th>Room</th>
              <th className="num">Qty</th>
              <th className="num">Cost</th>
              <th>Status</th>
              <th>Vendor / note</th>
            </tr>
          </thead>
          <tbody>
            {group.lines.map((line) => (
              <tr key={line.line_id}>
                <td className={line.overdue ? "text-danger" : ""}>{fmtDate(line.need_by)}</td>
                <td>{line.name}</td>
                <td className="muted">{line.room}</td>
                <td className="num">{line.qty != null ? `${line.qty} ${line.unit}` : "—"}</td>
                <td className="num">{money(line.cost)}</td>
                <td>
                  <select
                    className={`tag-select tag-buy-${line.buy_status.replace(/\s/g, "").toLowerCase()}`}
                    value={line.buy_status}
                    onChange={(e) => setBuyStatus(line.line_id, e.target.value as BuyStatus)}
                  >
                    {BUY_STATUSES.map((s) => (
                      <option key={s}>{s}</option>
                    ))}
                  </select>
                </td>
                <td>
                  <input
                    type="text"
                    defaultValue={line.notes}
                    placeholder="vendor / note…"
                    onBlur={(e) => {
                      if (e.target.value !== line.notes) setNotes(line.line_id, e.target.value);
                    }}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ))}
    </div>
  );
}
