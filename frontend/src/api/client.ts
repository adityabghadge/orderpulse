import type {
  ModelSummary,
  OrderDetail,
  OrderStatus,
  OrderSummary,
  OverviewStats,
  Page,
  Refund,
  ReturnCreate,
  ReturnReason,
  ReturnRecord,
  ReturnStatus,
  Team,
} from "./types";

/** An error response from the API, in its standard `{"error": {code, message}}` shape. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type Query = Record<string, string | number | undefined | null>;

function buildUrl(path: string, query?: Query): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  }
  const qs = params.toString();
  return `/api/v1${path}${qs ? `?${qs}` : ""}`;
}

async function request<T>(
  method: "GET" | "POST",
  path: string,
  options: { query?: Query; body?: unknown; headers?: Record<string, string> } = {},
): Promise<T> {
  const response = await fetch(buildUrl(path, options.query), {
    method,
    headers: {
      Accept: "application/json",
      ...(options.body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...options.headers,
    },
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const error = payload?.error;
    throw new ApiError(
      response.status,
      error?.code ?? "http_error",
      error?.message ?? `Request failed with status ${response.status}`,
    );
  }
  return (await response.json()) as T;
}

export const api = {
  overview: () => request<OverviewStats>("GET", "/stats/overview"),

  listOrders: (query: {
    status?: OrderStatus;
    q?: string;
    customer_id?: number;
    limit?: number;
    offset?: number;
  }) => request<Page<OrderSummary>>("GET", "/orders", { query }),

  getOrder: (orderNumber: string) => request<OrderDetail>("GET", `/orders/${orderNumber}`),

  changeOrderStatus: (orderNumber: string, status: OrderStatus, note?: string) =>
    request<OrderDetail>("POST", `/orders/${orderNumber}/status`, {
      body: { status, note: note || null },
    }),

  listReturns: (query: {
    status?: ReturnStatus;
    reason?: ReturnReason;
    order_number?: string;
    sort?: "newest" | "oldest" | "priority";
    limit?: number;
    offset?: number;
  }) => request<Page<ReturnRecord>>("GET", "/returns", { query }),

  reassignTeam: (returnNumber: string, team: Team) =>
    request<ReturnRecord>("POST", `/returns/${returnNumber}/team`, { body: { team } }),

  models: () => request<ModelSummary>("GET", "/ml/models"),

  getReturn: (returnNumber: string) => request<ReturnRecord>("GET", `/returns/${returnNumber}`),

  createReturn: (orderNumber: string, body: ReturnCreate) =>
    request<ReturnRecord>("POST", `/orders/${orderNumber}/returns`, { body }),

  changeReturnStatus: (
    returnNumber: string,
    status: "approved" | "rejected" | "received",
    note?: string,
  ) =>
    request<ReturnRecord>("POST", `/returns/${returnNumber}/status`, {
      body: { status, note: note || null },
    }),

  issueRefund: (returnNumber: string, idempotencyKey: string, note?: string) =>
    request<Refund>("POST", `/returns/${returnNumber}/refund`, {
      headers: { "Idempotency-Key": idempotencyKey },
      body: { note: note || null },
    }),
};
