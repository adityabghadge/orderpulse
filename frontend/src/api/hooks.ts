import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { refundWithRetry } from "../lib/refund";
import { api } from "./client";
import type { OrderStatus, ReturnCreate, ReturnReason, ReturnStatus, Team } from "./types";

// Query keys identify cached data. Invalidating a key makes every screen using it refetch.
export const keys = {
  overview: ["overview"] as const,
  orders: (params: object) => ["orders", params] as const,
  order: (orderNumber: string) => ["order", orderNumber] as const,
  returns: (params: object) => ["returns", params] as const,
  return: (returnNumber: string) => ["return", returnNumber] as const,
};

export function useOverview() {
  return useQuery({ queryKey: keys.overview, queryFn: api.overview, refetchInterval: 30_000 });
}

export function useModels() {
  return useQuery({ queryKey: ["models"], queryFn: api.models, staleTime: 5 * 60_000 });
}

export function useOrders(params: Parameters<typeof api.listOrders>[0]) {
  return useQuery({
    queryKey: keys.orders(params),
    queryFn: () => api.listOrders(params),
    placeholderData: keepPreviousData, // keep the old page on screen while the next loads
  });
}

export function useOrder(orderNumber: string) {
  return useQuery({ queryKey: keys.order(orderNumber), queryFn: () => api.getOrder(orderNumber) });
}

export function useReturns(params: {
  status?: ReturnStatus;
  reason?: ReturnReason;
  order_number?: string;
  sort?: "newest" | "oldest" | "priority";
  limit?: number;
  offset?: number;
}) {
  return useQuery({
    queryKey: keys.returns(params),
    queryFn: () => api.listReturns(params),
    placeholderData: keepPreviousData,
  });
}

export function useReturn(returnNumber: string | undefined) {
  return useQuery({
    queryKey: keys.return(returnNumber ?? ""),
    queryFn: () => api.getReturn(returnNumber!),
    enabled: Boolean(returnNumber),
  });
}

/** After any write, refresh every list and summary that might show the changed record. */
function useInvalidateAll() {
  const client = useQueryClient();
  return () =>
    Promise.all(
      ["overview", "orders", "order", "returns", "return"].map((key) =>
        client.invalidateQueries({ queryKey: [key] }),
      ),
    );
}

export function useChangeOrderStatus(orderNumber: string) {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: (status: OrderStatus) => api.changeOrderStatus(orderNumber, status),
    onSuccess: invalidate,
  });
}

export function useCreateReturn(orderNumber: string) {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: (body: ReturnCreate) => api.createReturn(orderNumber, body),
    onSuccess: invalidate,
  });
}

export function useChangeReturnStatus(returnNumber: string) {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: ({
      status,
      note,
    }: {
      status: "approved" | "rejected" | "received";
      note?: string;
    }) => api.changeReturnStatus(returnNumber, status, note),
    onSuccess: invalidate,
  });
}

export function useIssueRefund(returnNumber: string) {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: (note?: string) => refundWithRetry(returnNumber, { note }),
    onSuccess: invalidate,
  });
}

export function useReassignTeam(returnNumber: string) {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: (team: Team) => api.reassignTeam(returnNumber, team),
    onSuccess: invalidate,
  });
}
