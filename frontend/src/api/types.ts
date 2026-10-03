// TypeScript mirrors of the API's response shapes (backend/app/schemas).

export type OrderStatus =
  | "placed"
  | "packed"
  | "shipped"
  | "out_for_delivery"
  | "delivered"
  | "cancelled";

export type ReturnStatus = "requested" | "approved" | "rejected" | "received" | "refunded";

export type ReturnReason =
  | "damaged"
  | "defective"
  | "wrong_item"
  | "missing_parts"
  | "not_as_described"
  | "size_fit"
  | "late_delivery"
  | "changed_mind";

export type Team = "logistics" | "quality" | "fulfillment" | "customer_care";

export type PaymentMethod = "card" | "wallet" | "cod";

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface OrderSummary {
  id: number;
  order_number: string;
  customer_id: number;
  customer_name: string;
  status: OrderStatus;
  total_cents: number;
  currency: string;
  payment_method: PaymentMethod;
  shipping_city: string;
  placed_at: string;
  delivered_at: string | null;
  item_count: number;
}

export interface OrderItem {
  id: number;
  sku: string;
  product_name: string;
  category: string;
  quantity: number;
  unit_price_cents: number;
  line_total_cents: number;
}

export interface OrderEvent {
  id: number;
  from_status: OrderStatus | null;
  to_status: OrderStatus;
  note: string | null;
  actor: string;
  created_at: string;
}

export interface OrderDetail extends OrderSummary {
  customer: { id: number; full_name: string; email: string; tier: string };
  items: OrderItem[];
  events: OrderEvent[];
}

export interface Refund {
  id: number;
  return_number: string;
  amount_cents: number;
  currency: string;
  status: string;
  provider_reference: string;
  created_at: string;
}

export interface ReturnRecord {
  id: number;
  return_number: string;
  order_number: string;
  order_item_id: number;
  quantity: number;
  reason_code: ReturnReason;
  reason_text: string;
  status: ReturnStatus;
  assigned_team: Team | null;
  decision_note: string | null;
  refund_amount_cents: number;
  requested_at: string;
  resolved_at: string | null;
  refund: Refund | null;
}

export interface OverviewStats {
  pipeline: { status: OrderStatus; count: number }[];
  delivered_last_7d: number;
  cancelled_last_7d: number;
  orders_today: number;
  revenue_today_cents: number;
  open_returns: number;
  returns_by_status: Record<ReturnStatus, number>;
  refunded_30d_cents: number;
  refunds_30d: number;
  avg_delivery_hours_30d: number | null;
  orders_per_day: { day: string; orders: number; revenue_cents: number }[];
  open_returns_by_team: { team: Team; open_returns: number }[];
}

export interface ReturnCreate {
  order_item_id: number;
  quantity: number;
  reason_code: ReturnReason;
  reason_text: string;
}
