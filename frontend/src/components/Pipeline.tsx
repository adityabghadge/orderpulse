import { useNavigate } from "react-router-dom";

import type { OverviewStats } from "../api/types";
import { formatNumber, ORDER_STATUS_LABEL } from "../lib/format";
import { STAGE_CLASS } from "./StatusPill";

/** Orders currently in flight, one segment per stage, each sized by its share of volume. */
export function Pipeline({ stats }: { stats: OverviewStats }) {
  const navigate = useNavigate();
  const inFlight = stats.pipeline.reduce((sum, stage) => sum + stage.count, 0);

  return (
    <section className="panel pipeline" aria-labelledby="pipeline-title">
      <div className="panel-head" style={{ padding: 0 }}>
        <h2 id="pipeline-title">{formatNumber(inFlight)} orders on the way to customers</h2>
        <span className="hint">Select a stage to see its orders</span>
      </div>

      <div className="pipeline-track">
        {stats.pipeline.map((stage) => {
          const share = inFlight ? stage.count / inFlight : 0;
          return (
            <button
              key={stage.status}
              type="button"
              className={`stage ${STAGE_CLASS[stage.status]}`}
              style={{ flexGrow: Math.max(share, 0.08), flexBasis: 0 }}
              onClick={() => navigate(`/orders?status=${stage.status}`)}
              aria-label={`${ORDER_STATUS_LABEL[stage.status]}: ${stage.count} orders`}
            >
              <span className="stage-count">{formatNumber(stage.count)}</span>
              <span>
                <span className="stage-name">{ORDER_STATUS_LABEL[stage.status]}</span>
                <br />
                <span className="stage-share">{Math.round(share * 100)}% of in-flight</span>
              </span>
            </button>
          );
        })}
      </div>

      <div className="pipeline-foot">
        <span>
          <strong>{formatNumber(stats.delivered_last_7d)}</strong> delivered in the last 7 days
        </span>
        <span>
          <strong>{formatNumber(stats.cancelled_last_7d)}</strong> cancelled in the last 7 days
        </span>
      </div>
    </section>
  );
}
