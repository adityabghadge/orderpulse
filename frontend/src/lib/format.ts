import type { OrderStatus, ReturnReason, ReturnStatus, Team } from "../api/types";

const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const compactMoney = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  notation: "compact",
  maximumFractionDigits: 1,
});
const integer = new Intl.NumberFormat("en-US");

export const formatMoney = (cents: number) => money.format(cents / 100);
export const formatCompactMoney = (cents: number) => compactMoney.format(cents / 100);
export const formatNumber = (value: number) => integer.format(value);

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

/** "just now", "5 min ago", "3 h ago", "4 days ago" */
export function formatAge(iso: string, now: Date = new Date()): string {
  const minutes = Math.max(0, Math.round((now.getTime() - new Date(iso).getTime()) / 60000));
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  return `${days} ${days === 1 ? "day" : "days"} ago`;
}

export const ORDER_STATUS_LABEL: Record<OrderStatus, string> = {
  placed: "Placed",
  packed: "Packed",
  shipped: "Shipped",
  out_for_delivery: "Out for delivery",
  delivered: "Delivered",
  cancelled: "Cancelled",
};

export const RETURN_STATUS_LABEL: Record<ReturnStatus, string> = {
  requested: "Needs review",
  approved: "Awaiting item",
  received: "Ready to refund",
  refunded: "Refunded",
  rejected: "Rejected",
};

export const REASON_LABEL: Record<ReturnReason, string> = {
  damaged: "Damaged in transit",
  defective: "Defective",
  wrong_item: "Wrong item",
  missing_parts: "Missing parts",
  not_as_described: "Not as described",
  size_fit: "Size or fit",
  late_delivery: "Late delivery",
  changed_mind: "Changed mind",
};

export const TEAM_LABEL: Record<Team, string> = {
  logistics: "Logistics",
  quality: "Quality",
  fulfillment: "Fulfillment",
  customer_care: "Customer care",
};

export const PAYMENT_LABEL = { card: "Card", wallet: "Wallet", cod: "Cash on delivery" };

/** The next step in the delivery flow, mirroring the backend's state machine. */
export const NEXT_ORDER_STATUS: Partial<Record<OrderStatus, OrderStatus>> = {
  placed: "packed",
  packed: "shipped",
  shipped: "out_for_delivery",
  out_for_delivery: "delivered",
};

export const CANCELLABLE: OrderStatus[] = ["placed", "packed"];

export const ADVANCE_LABEL: Partial<Record<OrderStatus, string>> = {
  packed: "Mark as packed",
  shipped: "Mark as shipped",
  out_for_delivery: "Send out for delivery",
  delivered: "Mark as delivered",
};
