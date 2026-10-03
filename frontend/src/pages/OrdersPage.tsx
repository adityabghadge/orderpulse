import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { useOrders } from "../api/hooks";
import type { OrderStatus } from "../api/types";
import { EmptyState, ErrorState, Pager, TableSkeleton } from "../components/States";
import { OrderStatusPill } from "../components/StatusPill";
import { formatDateTime, formatMoney, ORDER_STATUS_LABEL, PAYMENT_LABEL } from "../lib/format";

const FILTERS: (OrderStatus | "all")[] = [
  "all",
  "placed",
  "packed",
  "shipped",
  "out_for_delivery",
  "delivered",
  "cancelled",
];
const PAGE_SIZE = 25;

export function OrdersPage() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const status = (params.get("status") as OrderStatus | null) ?? undefined;
  const q = params.get("q") ?? "";
  const offset = Number(params.get("offset") ?? 0);
  const [search, setSearch] = useState(q);

  // Wait until typing pauses before searching, instead of querying on every keystroke.
  useEffect(() => {
    const timer = setTimeout(() => {
      if (search !== q) update({ q: search || undefined, offset: undefined });
    }, 300);
    return () => clearTimeout(timer);
  }, [search]);

  function update(changes: Record<string, string | number | undefined>) {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      if (value === undefined || value === "" || value === 0) next.delete(key);
      else next.set(key, String(value));
    }
    setParams(next, { replace: true });
  }

  const { data, isLoading, isError, error, refetch, isFetching } = useOrders({
    status,
    q: q || undefined,
    limit: PAGE_SIZE,
    offset,
  });

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Orders</h1>
          <p className="sub">
            {data ? `${data.total.toLocaleString()} orders` : "Loading orders"}
            {status ? ` ${ORDER_STATUS_LABEL[status].toLowerCase()}` : ""}
          </p>
        </div>
      </div>

      <div className="toolbar">
        <div className="segmented" role="group" aria-label="Filter by status">
          {FILTERS.map((value) => (
            <button
              key={value}
              type="button"
              aria-pressed={(status ?? "all") === value}
              onClick={() =>
                update({ status: value === "all" ? undefined : value, offset: undefined })
              }
            >
              {value === "all" ? "All" : ORDER_STATUS_LABEL[value]}
            </button>
          ))}
        </div>
        <label className="visually-hidden" htmlFor="order-search">
          Search orders
        </label>
        <input
          id="order-search"
          className="input search"
          type="search"
          placeholder="Search by order number or city"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      <section className="panel" aria-busy={isFetching}>
        {isError ? (
          <ErrorState error={error} onRetry={refetch} />
        ) : data && data.items.length === 0 ? (
          <EmptyState title="No orders match these filters">
            Try a different status or clear the search.
          </EmptyState>
        ) : (
          <>
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Order</th>
                    <th>Customer</th>
                    <th>Placed</th>
                    <th className="num">Items</th>
                    <th className="num">Total</th>
                    <th>Payment</th>
                    <th>Ship to</th>
                    <th>Status</th>
                  </tr>
                </thead>
                {isLoading || !data ? (
                  <TableSkeleton columns={8} />
                ) : (
                  <tbody>
                    {data.items.map((order) => (
                      <tr
                        key={order.id}
                        className="clickable"
                        onClick={() => navigate(`/orders/${order.order_number}`)}
                      >
                        <td className="strong">
                          <Link
                            to={`/orders/${order.order_number}`}
                            onClick={(e) => e.stopPropagation()}
                          >
                            {order.order_number}
                          </Link>
                        </td>
                        <td>{order.customer_name}</td>
                        <td className="muted">{formatDateTime(order.placed_at)}</td>
                        <td className="num">{order.item_count}</td>
                        <td className="num strong">{formatMoney(order.total_cents)}</td>
                        <td>{PAYMENT_LABEL[order.payment_method]}</td>
                        <td>{order.shipping_city}</td>
                        <td>
                          <OrderStatusPill status={order.status} />
                        </td>
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
    </>
  );
}
