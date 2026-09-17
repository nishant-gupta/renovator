import { api } from "../api/client";
import { useFetch } from "../api/hooks";
import { StatRow, Stat } from "../components/Stat";
import { money } from "../format";
import type { SumPair } from "../api/types";

function BarRows({ pairs }: { pairs: SumPair[] }) {
  const max = Math.max(1, ...pairs.map(([, v]) => v));
  return (
    <div className="bar-rows">
      {pairs.length === 0 && <div className="empty">No items yet</div>}
      {pairs.map(([label, value]) => (
        <div className="bar-row" key={label}>
          <div className="bar-label">{label}</div>
          <div className="bar-track">
            <div className="bar-fill" style={{ width: `${Math.max(2, (value / max) * 100)}%` }} />
          </div>
          <div className="bar-value">{money(value)}</div>
        </div>
      ))}
    </div>
  );
}

export function EstimateTab({ projectId, planVersion }: { projectId: string; planVersion: number }) {
  const { data: estimate, error, loading } = useFetch(
    () => api.getEstimate(projectId),
    [projectId, planVersion],
  );

  if (loading) return <div className="empty">Loading…</div>;
  if (error) return <div className="empty empty-error">Couldn't load estimate: {error}</div>;
  if (!estimate) return null;

  return (
    <div>
      <h1 className="page-h">Estimate</h1>
      <p className="page-sub">Derived live from your tasks and the rate card.</p>

      <StatRow>
        <Stat label="Grand total" value={money(estimate.total)} />
        <Stat label="Mandatory" value={money(estimate.mandatory)} />
        <Stat label="Optional" value={money(estimate.optional)} />
        <Stat label="Materials" value={money(estimate.materials)} />
      </StatRow>

      <div className="sect">Cost by room</div>
      <BarRows pairs={estimate.by_room} />
      <div className="sect">Cost by trade</div>
      <BarRows pairs={estimate.by_trade} />
      <div className="sect">Cost by phase</div>
      <BarRows pairs={estimate.by_phase} />

      <div className="sect">All tasks</div>
      <table className="dt">
        <thead>
          <tr>
            <th>Room</th>
            <th>Task</th>
            <th className="num">Cost</th>
          </tr>
        </thead>
        <tbody>
          {estimate.tasks.length === 0 && (
            <tr>
              <td colSpan={3} className="empty-cell">
                No tasks match.
              </td>
            </tr>
          )}
          {estimate.tasks.map((task) => (
            <tr key={task.task_id}>
              <td>{task.room}</td>
              <td>{task.name}</td>
              <td className="num">{money(task.total_cost)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
