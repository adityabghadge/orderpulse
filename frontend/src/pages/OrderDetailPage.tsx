import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";

import { ApiError } from "../api/client";
import { useChangeOrderStatus, useCreateReturn, useOrder, useReturns } from "../api/hooks";
import type { OrderDetail, OrderItem, ReturnReason } from "../api/types";
import { ErrorState } from "../components/States";
import { OrderStatusPill, ReturnStatusPill } from "../components/StatusPill";
import { useToast } from "../components/Toasts";
import {
  ADVANCE_LABEL,
  CANCELLABLE,
  formatDateTime,
  formatMoney,
  NEXT_ORDER_STATUS,
  ORDER_STATUS_LABEL,
  PAYMENT_LABEL,
  REASON_LABEL,
  TEAM_LABEL,
} from "../lib/format";

const RETURN_WINDOW_DAYS = 30;

function errorMessage(error: unknown) {
  return error instanceof ApiError ? error.message : "Something went wrong. Try again.";
}

function StatusActions({ order }: { order: OrderDetail }) {
  const notify = useToast();
  const mutation = useChangeOrderStatus(order.order_number);
  const next = NEXT_ORDER_STATUS[order.status];

  const run = (status: typeof order.status) =>
    mutation.mutate(status, {
      onSuccess: () => notify(`${order.order_number} is now ${ORDER_STATUS_LABEL[status].toLowerCase()}`),
      onError: (error) => notify(errorMessage(error), "error"),
    });

  if (!next && !CANCELLABLE.includes(order.status)) return null;
  return (
    <div className="actions">
      {next && (
        <button className="btn btn-primary" disabled={mutation.isPending} onClick={() => run(next)}>
          {ADVANCE_LABEL[next]}
        </button>
      )}
      {CANCELLABLE.includes(order.status) && (
        <button
          className="btn btn-danger"
          disabled={mutation.isPending}
          onClick={() => run("cancelled")}
        >
          Cancel order
        </button>
      )}
    </div>
  );
}

function ReturnForm({
  order,
  item,
  onDone,
}: {
  order: OrderDetail;
  item: OrderItem;
  onDone: () => void;
}) {
  const notify = useToast();
  const mutation = useCreateReturn(order.order_number);
  const [quantity, setQuantity] = useState(1);
  const [reason, setReason] = useState<ReturnReason>("damaged");
  const [text, setText] = useState("");

  function submit(event: FormEvent) {
    event.preventDefault();
    mutation.mutate(
      { order_item_id: item.id, quantity, reason_code: reason, reason_text: text },
      {
        onSuccess: (created) => {
          notify(`Return ${created.return_number} created`);
          onDone();
        },
      },
    );
  }

  return (
    <form className="return-form" onSubmit={submit}>
      <h3>Return {item.product_name}</h3>
      <div className="form-row">
        <div className="field">
          <label htmlFor="return-qty">Quantity</label>
          <select
            id="return-qty"
            className="select"
            value={quantity}
            onChange={(e) => setQuantity(Number(e.target.value))}
          >
            {Array.from({ length: item.quantity }, (_, i) => i + 1).map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="return-reason">Reason</label>
          <select
            id="return-reason"
            className="select"
            value={reason}
            onChange={(e) => setReason(e.target.value as ReturnReason)}
          >
            {Object.entries(REASON_LABEL).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div className="field">
        <label htmlFor="return-text">What happened, in the customer's words</label>
        <textarea
          id="return-text"
          className="textarea"
          minLength={10}
          maxLength={1000}
          required
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="For example: the box arrived crushed and the screen is cracked."
        />
      </div>
      {mutation.isError && <p className="notice error">{errorMessage(mutation.error)}</p>}
      <div className="actions">
        <button className="btn btn-primary" type="submit" disabled={mutation.isPending}>
          Create return
        </button>
        <button className="btn btn-secondary" type="button" onClick={onDone}>
          Cancel
        </button>
      </div>
    </form>
  );
}

function ItemsPanel({ order }: { order: OrderDetail }) {
  const [returningItem, setReturningItem] = useState<number | null>(null);
  const deliveredAt = order.delivered_at ? new Date(order.delivered_at) : null;
  const windowOpen =
    deliveredAt !== null &&
    Date.now() - deliveredAt.getTime() < RETURN_WINDOW_DAYS * 24 * 60 * 60 * 1000;
  const selected = order.items.find((i) => i.id === returningItem);

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Items</h2>
        {order.status === "delivered" && (
          <span className="hint">
            {windowOpen ? "Return window open" : "Return window closed"}
          </span>
        )}
      </div>
      <div className="panel-body" style={{ paddingTop: 8 }}>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Product</th>
                <th className="num">Qty</th>
                <th className="num">Price</th>
                <th className="num">Total</th>
                {windowOpen && <th />}
              </tr>
            </thead>
            <tbody>
              {order.items.map((item) => (
                <tr key={item.id}>
                  <td>
                    <div className="strong">{item.product_name}</div>
                    <div className="muted" style={{ fontSize: "0.85rem" }}>
                      {item.sku}
                    </div>
                  </td>
                  <td className="num">{item.quantity}</td>
                  <td className="num">{formatMoney(item.unit_price_cents)}</td>
                  <td className="num strong">{formatMoney(item.line_total_cents)}</td>
                  {windowOpen && (
                    <td className="num">
                      <button
                        className="btn btn-secondary btn-small"
                        onClick={() => setReturningItem(item.id)}
                      >
                        Start a return
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {selected && (
          <ReturnForm order={order} item={selected} onDone={() => setReturningItem(null)} />
        )}
      </div>
    </section>
  );
}

function OrderReturns({ orderNumber }: { orderNumber: string }) {
  const { data } = useReturns({ order_number: orderNumber, limit: 20 });
  if (!data || data.items.length === 0) return null;
  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Returns on this order</h2>
      </div>
      <div className="panel-body" style={{ paddingTop: 8 }}>
        <table className="table">
          <tbody>
            {data.items.map((r) => (
              <tr key={r.id}>
                <td className="strong">
                  <Link to={`/returns?selected=${r.return_number}`}>{r.return_number}</Link>
                </td>
                <td>{REASON_LABEL[r.reason_code]}</td>
                <td>{r.assigned_team ? TEAM_LABEL[r.assigned_team] : "–"}</td>
                <td className="num">{formatMoney(r.refund_amount_cents)}</td>
                <td>
                  <ReturnStatusPill status={r.status} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function OrderDetailPage() {
  const { orderNumber = "" } = useParams();
  const { data: order, isLoading, isError, error, refetch } = useOrder(orderNumber);

  return (
    <>
      <Link to="/orders" className="back">
        All orders
      </Link>
      {isError ? (
        <section className="panel">
          <ErrorState error={error} onRetry={refetch} />
        </section>
      ) : isLoading || !order ? (
        <div className="skeleton" style={{ height: 48, width: 320 }} />
      ) : (
        <>
          <div className="page-head">
            <div>
              <div className="detail-head">
                <h1>{order.order_number}</h1>
                <OrderStatusPill status={order.status} />
              </div>
              <p className="sub">
                Placed {formatDateTime(order.placed_at)} by {order.customer.full_name}
              </p>
            </div>
            <StatusActions order={order} />
          </div>

          <div className="split">
            <div className="stack">
              <ItemsPanel order={order} />
              <OrderReturns orderNumber={order.order_number} />
            </div>
            <div className="stack">
              <section className="panel">
                <div className="panel-head">
                  <h2>Summary</h2>
                </div>
                <div className="panel-body">
                  <dl className="facts">
                    <dt>Customer</dt>
                    <dd>{order.customer.full_name}</dd>
                    <dt>Email</dt>
                    <dd>{order.customer.email}</dd>
                    <dt>Membership</dt>
                    <dd>{order.customer.tier === "plus" ? "Plus member" : "Standard"}</dd>
                    <dt>Ship to</dt>
                    <dd>{order.shipping_city}</dd>
                    <dt>Payment</dt>
                    <dd>{PAYMENT_LABEL[order.payment_method]}</dd>
                    <dt>Total</dt>
                    <dd>{formatMoney(order.total_cents)}</dd>
                  </dl>
                </div>
              </section>
              <section className="panel">
                <div className="panel-head">
                  <h2>History</h2>
                </div>
                <div className="panel-body">
                  <ol className="timeline">
                    {[...order.events].reverse().map((event) => (
                      <li key={event.id}>
                        <div className="strong">{ORDER_STATUS_LABEL[event.to_status]}</div>
                        <div className="when">
                          {formatDateTime(event.created_at)} by {event.actor}
                        </div>
                        {event.note && <div className="muted">{event.note}</div>}
                      </li>
                    ))}
                  </ol>
                </div>
              </section>
            </div>
          </div>
        </>
      )}
    </>
  );
}
