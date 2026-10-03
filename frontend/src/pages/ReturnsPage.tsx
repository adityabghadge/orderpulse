import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { ApiError } from "../api/client";
import {
  useChangeReturnStatus,
  useIssueRefund,
  useReassignTeam,
  useReturn,
  useReturns,
} from "../api/hooks";
import type { ReturnReason, ReturnRecord, ReturnStatus, Team } from "../api/types";
import { EmptyState, ErrorState, Pager, TableSkeleton } from "../components/States";
import { PriorityPill, ReturnStatusPill } from "../components/StatusPill";
import { useToast } from "../components/Toasts";
import {
  formatAge,
  formatDateTime,
  formatMoney,
  REASON_LABEL,
  RETURN_STATUS_LABEL,
  TEAM_LABEL,
} from "../lib/format";

const QUEUES: { value: ReturnStatus | "all"; label: string }[] = [
  { value: "requested", label: RETURN_STATUS_LABEL.requested },
  { value: "approved", label: RETURN_STATUS_LABEL.approved },
  { value: "received", label: RETURN_STATUS_LABEL.received },
  { value: "refunded", label: RETURN_STATUS_LABEL.refunded },
  { value: "rejected", label: RETURN_STATUS_LABEL.rejected },
  { value: "all", label: "All" },
];
const OPEN: (ReturnStatus | "all")[] = ["requested", "approved", "received"];
const PAGE_SIZE = 20;

function errorMessage(error: unknown) {
  return error instanceof ApiError ? error.message : "Something went wrong. Try again.";
}

function ReturnActions({ record }: { record: ReturnRecord }) {
  const notify = useToast();
  const statusChange = useChangeReturnStatus(record.return_number);
  const refund = useIssueRefund(record.return_number);
  const [rejecting, setRejecting] = useState(false);
  const [note, setNote] = useState("");
  const busy = statusChange.isPending || refund.isPending;

  const change = (status: "approved" | "rejected" | "received", successMessage: string) =>
    statusChange.mutate(
      { status, note: note || undefined },
      {
        onSuccess: () => {
          notify(successMessage);
          setRejecting(false);
          setNote("");
        },
        onError: (error) => notify(errorMessage(error), "error"),
      },
    );

  if (record.status === "requested") {
    return rejecting ? (
      <div className="stack" style={{ gap: 10 }}>
        <div className="field">
          <label htmlFor="reject-note">Reason for rejecting (shared with the customer)</label>
          <textarea
            id="reject-note"
            className="textarea"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
        </div>
        <div className="actions">
          <button
            className="btn btn-danger"
            disabled={busy || note.trim().length === 0}
            onClick={() => change("rejected", `${record.return_number} rejected`)}
          >
            Reject return
          </button>
          <button className="btn btn-secondary" onClick={() => setRejecting(false)}>
            Back
          </button>
        </div>
      </div>
    ) : (
      <div className="actions">
        <button
          className="btn btn-primary"
          disabled={busy}
          onClick={() => change("approved", `${record.return_number} approved`)}
        >
          Approve return
        </button>
        <button className="btn btn-danger" disabled={busy} onClick={() => setRejecting(true)}>
          Reject
        </button>
      </div>
    );
  }

  if (record.status === "approved") {
    return (
      <button
        className="btn btn-primary"
        disabled={busy}
        onClick={() => change("received", `${record.return_number} marked as received`)}
      >
        Mark item as received
      </button>
    );
  }

  if (record.status === "received") {
    return (
      <div className="stack" style={{ gap: 10 }}>
        <button
          className="btn btn-primary"
          disabled={busy}
          onClick={() =>
            refund.mutate(undefined, {
              onSuccess: ({ refund: issued }) =>
                notify(`Refunded ${formatMoney(issued.amount_cents)} for ${record.return_number}`),
              onError: (error) => notify(errorMessage(error), "error"),
            })
          }
        >
          {refund.isPending
            ? "Issuing refund…"
            : `Refund ${formatMoney(record.refund_amount_cents)}`}
        </button>
        <p className="muted" style={{ fontSize: "0.85rem" }}>
          Safe to retry: a connection drop or provider timeout is retried with the same
          idempotency key, so the customer is never paid twice.
        </p>
      </div>
    );
  }

  return null;
}

function routingExplanation(record: ReturnRecord): string {
  if (record.routing_source === "model" && record.routing_confidence !== null) {
    const percent = Math.min(99, Math.round(record.routing_confidence * 100));
    return `Routed by the model from the customer's words (${percent}% confident)`;
  }
  if (record.routing_source === "agent") return "Assigned by an agent";
  return "Routed by the reason the customer selected";
}

function TeamControl({ record }: { record: ReturnRecord }) {
  const notify = useToast();
  const reassign = useReassignTeam(record.return_number);
  const [team, setTeam] = useState<Team>(record.assigned_team ?? "customer_care");
  const isOpen = ["requested", "approved", "received"].includes(record.status);
  if (!isOpen) return null;
  return (
    <div className="field">
      <label htmlFor="team-select">Send to another team</label>
      <div className="inline-form">
        <select
          id="team-select"
          className="select"
          value={team}
          onChange={(e) => setTeam(e.target.value as Team)}
        >
          {Object.entries(TEAM_LABEL).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        <button
          className="btn btn-secondary"
          disabled={reassign.isPending || team === record.assigned_team}
          onClick={() =>
            reassign.mutate(team, {
              onSuccess: () => notify(`${record.return_number} sent to ${TEAM_LABEL[team]}`),
              onError: (error) => notify(errorMessage(error), "error"),
            })
          }
        >
          Reassign
        </button>
      </div>
    </div>
  );
}

function ReturnPanel({ returnNumber }: { returnNumber: string }) {
  const { data: record, isLoading, isError, error, refetch } = useReturn(returnNumber);

  if (isError) return <ErrorState error={error} onRetry={refetch} />;
  if (isLoading || !record) return <div className="panel-body"><div className="skeleton" /></div>;

  return (
    <>
      <div className="panel-head">
        <div>
          <h2 style={{ fontSize: "1.5rem" }}>{record.return_number}</h2>
          <p className="muted" style={{ marginTop: 2 }}>
            Order <Link to={`/orders/${record.order_number}`}>{record.order_number}</Link>,
            requested {formatAge(record.requested_at)}
          </p>
        </div>
        <ReturnStatusPill status={record.status} />
      </div>
      <div className="panel-body stack">
        <blockquote className="quote">{record.reason_text}</blockquote>
        <dl className="facts">
          <dt>Reason selected</dt>
          <dd>{REASON_LABEL[record.reason_code]}</dd>
          <dt>Handled by</dt>
          <dd>
            {record.assigned_team ? TEAM_LABEL[record.assigned_team] : "Unassigned"}
            <div className="muted" style={{ fontWeight: 400, fontSize: "0.82rem" }}>
              {routingExplanation(record)}
            </div>
          </dd>
          {record.priority_score !== null && (
            <>
              <dt>Escalation risk</dt>
              <dd>
                <PriorityPill priority={record.priority} />{" "}
                <span className="muted" style={{ fontWeight: 400 }}>
                  {Math.round(record.priority_score * 100)}% chance
                </span>
              </dd>
            </>
          )}
          <dt>Units</dt>
          <dd>{record.quantity}</dd>
          <dt>Refund amount</dt>
          <dd>{formatMoney(record.refund_amount_cents)}</dd>
          {record.resolved_at && (
            <>
              <dt>Closed</dt>
              <dd>{formatDateTime(record.resolved_at)}</dd>
            </>
          )}
        </dl>
        {record.decision_note && <p className="notice info">{record.decision_note}</p>}
        {record.refund && (
          <div className="notice info">
            Refunded {formatMoney(record.refund.amount_cents)} on{" "}
            {formatDateTime(record.refund.created_at)}. Provider reference{" "}
            <strong>{record.refund.provider_reference}</strong>.
          </div>
        )}
        <ReturnActions record={record} />
        <TeamControl record={record} />
      </div>
    </>
  );
}

export function ReturnsPage() {
  const [params, setParams] = useSearchParams();
  const queue = (params.get("status") as ReturnStatus | "all" | null) ?? "requested";
  const reason = (params.get("reason") as ReturnReason | null) ?? undefined;
  const offset = Number(params.get("offset") ?? 0);
  const selected = params.get("selected") ?? undefined;
  const isOpenQueue = OPEN.includes(queue);
  // Open work defaults to riskiest first; operators can switch to first-in, first-out.
  const sort = (params.get("sort") as "priority" | "oldest" | null) ?? "priority";

  function update(changes: Record<string, string | number | undefined>) {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      if (value === undefined || value === "" || value === 0) next.delete(key);
      else next.set(key, String(value));
    }
    setParams(next, { replace: true });
  }

  const { data, isLoading, isError, error, refetch } = useReturns({
    status: queue === "all" ? undefined : queue,
    reason,
    sort: isOpenQueue ? sort : "newest",
    limit: PAGE_SIZE,
    offset,
  });

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Returns</h1>
          <p className="sub">
            {!isOpenQueue
              ? "Most recent first"
              : sort === "priority"
                ? "Riskiest first, by predicted chance the customer escalates"
                : "Oldest first, so nothing waits too long"}
          </p>
        </div>
      </div>

      <div className="toolbar">
        <div className="segmented" role="group" aria-label="Queue">
          {QUEUES.map((q) => (
            <button
              key={q.value}
              type="button"
              aria-pressed={queue === q.value}
              onClick={() => update({ status: q.value, offset: undefined, selected: undefined })}
            >
              {q.label}
            </button>
          ))}
        </div>
        {isOpenQueue && (
          <>
            <label className="visually-hidden" htmlFor="sort-select">
              Sort
            </label>
            <select
              id="sort-select"
              className="select"
              value={sort}
              onChange={(e) => update({ sort: e.target.value, offset: undefined })}
            >
              <option value="priority">Highest risk first</option>
              <option value="oldest">Oldest first</option>
            </select>
          </>
        )}
        <label className="visually-hidden" htmlFor="reason-filter">
          Filter by reason
        </label>
        <select
          id="reason-filter"
          className="select"
          value={reason ?? ""}
          onChange={(e) => update({ reason: e.target.value || undefined, offset: undefined })}
        >
          <option value="">Any reason</option>
          {Object.entries(REASON_LABEL).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </div>

      <div className="split">
        <section className="panel">
          {isError ? (
            <ErrorState error={error} onRetry={refetch} />
          ) : data && data.items.length === 0 ? (
            <EmptyState title="Nothing in this queue">
              New returns appear here as customers request them.
            </EmptyState>
          ) : (
            <>
              <div className="table-wrap">
                <table className="table compact">
                  <thead>
                    <tr>
                      <th>Return</th>
                      <th>Reason</th>
                      <th>Team</th>
                      <th>Risk</th>
                      <th className="num">Amount</th>
                      <th>Requested</th>
                      {queue === "all" && <th>Status</th>}
                    </tr>
                  </thead>
                  {isLoading || !data ? (
                    <TableSkeleton columns={queue === "all" ? 7 : 6} />
                  ) : (
                    <tbody>
                      {data.items.map((r) => (
                        <tr
                          key={r.id}
                          className={`clickable ${selected === r.return_number ? "selected" : ""}`}
                          onClick={() => update({ selected: r.return_number })}
                        >
                          <td className="strong">
                            <button
                              type="button"
                              className="linklike"
                              onClick={(e) => {
                                e.stopPropagation();
                                update({ selected: r.return_number });
                              }}
                            >
                              {r.return_number}
                            </button>
                          </td>
                          <td>{REASON_LABEL[r.reason_code]}</td>
                          <td>{r.assigned_team ? TEAM_LABEL[r.assigned_team] : "–"}</td>
                          <td>
                            <PriorityPill priority={r.priority} />
                          </td>
                          <td className="num">{formatMoney(r.refund_amount_cents)}</td>
                          <td className="muted">{formatAge(r.requested_at)}</td>
                          {queue === "all" && (
                            <td>
                              <ReturnStatusPill status={r.status} />
                            </td>
                          )}
                        </tr>
                      ))}
                    </tbody>
                  )}
                </table>
              </div>
              {data && (
                <Pager
                  total={data.total}
                  limit={PAGE_SIZE}
                  offset={offset}
                  onChange={(next) => update({ offset: next })}
                />
              )}
            </>
          )}
        </section>

        <section className="panel sticky" aria-live="polite">
          {selected ? (
            <ReturnPanel returnNumber={selected} />
          ) : (
            <EmptyState title="Select a return">
              Its details, the customer's explanation, and the next action appear here.
            </EmptyState>
          )}
        </section>
      </div>
    </>
  );
}
