import type { OrderStatus, ReturnStatus } from "../api/types";
import { ORDER_STATUS_LABEL, RETURN_STATUS_LABEL } from "../lib/format";

// Darker = further along. Grey = stopped (cancelled / rejected).
const ORDER_STEP: Record<OrderStatus, string> = {
  placed: "step-1",
  packed: "step-2",
  shipped: "step-3",
  out_for_delivery: "step-4",
  delivered: "step-5",
  cancelled: "muted-fill",
};

const RETURN_STEP: Record<ReturnStatus, string> = {
  requested: "step-1",
  approved: "step-2",
  received: "step-3",
  refunded: "step-5",
  rejected: "muted-fill",
};

export function OrderStatusPill({ status }: { status: OrderStatus }) {
  return <span className={`pill ${ORDER_STEP[status]}`}>{ORDER_STATUS_LABEL[status]}</span>;
}

export function ReturnStatusPill({ status }: { status: ReturnStatus }) {
  return <span className={`pill ${RETURN_STEP[status]}`}>{RETURN_STATUS_LABEL[status]}</span>;
}

export const STAGE_CLASS = ORDER_STEP;
