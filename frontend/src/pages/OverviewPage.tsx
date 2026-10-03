import { Link, useNavigate } from "react-router-dom";

import { useOverview, useReturns } from "../api/hooks";
import type { OverviewStats } from "../api/types";
import { OrdersChart } from "../components/OrdersChart";
import { Pipeline } from "../components/Pipeline";
import { ErrorState, TableSkeleton } from "../components/States";
import { ReturnStatusPill } from "../components/StatusPill";
import {
  formatAge,
  formatCompactMoney,
  formatMoney,
  formatNumber,
  REASON_LABEL,
  TEAM_LABEL,
} from "../lib/format";

function Metrics({ stats }: { stats: OverviewStats }) {
  const awaitingRefund = stats.returns_by_status.received;
  return (
    <section className="panel metrics" aria-label="Key numbers">
      <div className="metric">
        <span className="value">{formatNumber(stats.orders_today)}</span>
        <span className="label">Orders today</span>
        <div className="detail">{formatMoney(stats.revenue_today_cents)} in sales</div>
      </div>
      <div className="metric">
        <span className="value">{formatNumber(stats.open_returns)}</span>
        <span className="label">Open returns</span>
        <div className="detail">{stats.returns_by_status.requested} need review</div>
      </div>
      <div className="metric">
        <span className="value">{formatNumber(awaitingRefund)}</span>
        <span className="label">Ready to refund</span>
        <div className="detail">Items back at the warehouse</div>
      </div>
      <div className="metric">
        <span className="value">{formatCompactMoney(stats.refunded_30d_cents)}</span>
        <span className="label">Refunded, last 30 days</span>
        <div className="detail">{formatNumber(stats.refunds_30d)} refunds</div>
      </div>
      <div className="metric">
        <span className="value">
          {stats.avg_delivery_hours_30d === null
            ? "–"
            : `${Math.round(stats.avg_delivery_hours_30d)} h`}
        </span>
        <span className="label">Average time to deliver</span>
        <div className="detail">Orders delivered in the last 30 days</div>
      </div>
    </section>
  );
}

function TeamLoad({ stats }: { stats: OverviewStats }) {
  const max = Math.max(1, ...stats.open_returns_by_team.map((t) => t.open_returns));
  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Open returns by team</h2>
      </div>
      <div className="panel-body">
        <div className="bars">
          {stats.open_returns_by_team.map((row) => (
            <div className="bar-row" key={row.team}>
              <span>{TEAM_LABEL[row.team]}</span>
              <div className="bar-track" aria-hidden="true">
                <div className="bar-fill" style={{ width: `${(row.open_returns / max) * 100}%` }} />
              </div>
              <span className="num">{formatNumber(row.open_returns)}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function ReviewQueue() {
  const navigate = useNavigate();
  const { data, isLoading, isError, error, refetch } = useReturns({
    status: "requested",
    sort: "oldest",
    limit: 6,
  });

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Waiting longest for review</h2>
        <Link to="/returns" className="hint">
          Open the returns queue
        </Link>
      </div>
      <div className="panel-body" style={{ padding: "8px 6px 6px" }}>
        {isError ? (
          <ErrorState error={error} onRetry={refetch} />
        ) : data && data.items.length === 0 ? (
          <p className="state">Every return has been reviewed.</p>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Return</th>
                  <th>Reason</th>
                  <th>Customer says</th>
                  <th>Team</th>
                  <th>Waiting</th>
                  <th>Status</th>
                </tr>
              </thead>
              {isLoading || !data ? (
                <TableSkeleton rows={5} columns={6} />
              ) : (
                <tbody>
                  {data.items.map((r) => (
                    <tr
                      key={r.id}
                      className="clickable"
                      onClick={() => navigate(`/returns?selected=${r.return_number}`)}
                    >
                      <td className="strong">
                        <Link
                          to={`/returns?selected=${r.return_number}`}
                          onClick={(e) => e.stopPropagation()}
                        >
                          {r.return_number}
                        </Link>
                      </td>
                      <td>{REASON_LABEL[r.reason_code]}</td>
                      <td className="truncate muted">{r.reason_text}</td>
                      <td>{r.assigned_team ? TEAM_LABEL[r.assigned_team] : "–"}</td>
                      <td>{formatAge(r.requested_at)}</td>
                      <td>
                        <ReturnStatusPill status={r.status} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              )}
            </table>
          </div>
        )}
      </div>
    </section>
  );
}

export function OverviewPage() {
  const { data, isLoading, isError, error, refetch, dataUpdatedAt } = useOverview();

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Operations overview</h1>
          <p className="sub">
            {dataUpdatedAt
              ? `Updated ${new Date(dataUpdatedAt).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })}, refreshes every 30 seconds`
              : "Loading live numbers"}
          </p>
        </div>
      </div>

      {isError ? (
        <section className="panel">
          <ErrorState error={error} onRetry={refetch} />
        </section>
      ) : isLoading || !data ? (
        <section className="panel pipeline">
          <div className="skeleton" style={{ height: 150 }} />
        </section>
      ) : (
        <div className="stack">
          <Pipeline stats={data} />
          <Metrics stats={data} />
          <div className="grid-2-1">
            <section className="panel">
              <div className="panel-head">
                <h2>Orders per day</h2>
                <span className="hint">Last 30 days</span>
              </div>
              <div className="panel-body">
                <OrdersChart data={data.orders_per_day} />
              </div>
            </section>
            <TeamLoad stats={data} />
          </div>
          <ReviewQueue />
        </div>
      )}
    </>
  );
}
