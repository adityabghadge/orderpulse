import { ApiError, api } from "../api/client";
import type { Refund } from "../api/types";

/** Failures worth retrying: the network dropped, or the payment provider had a hiccup. */
export function isRetryable(error: unknown): boolean {
  if (error instanceof ApiError) return [502, 503, 504].includes(error.status);
  return error instanceof TypeError; // fetch() throws TypeError when the network fails
}

interface RefundOptions {
  note?: string;
  /** One key per refund attempt. Every retry of that attempt reuses it. */
  idempotencyKey?: string;
  attempts?: number;
  baseDelayMs?: number;
  send?: (returnNumber: string, key: string, note?: string) => Promise<Refund>;
}

/**
 * Issue a refund, retrying transient failures with the SAME idempotency key.
 *
 * Because the key never changes between retries, the server pays at most once even if an
 * earlier attempt actually succeeded and only its response was lost.
 */
export async function refundWithRetry(
  returnNumber: string,
  {
    note,
    idempotencyKey = crypto.randomUUID(),
    attempts = 3,
    baseDelayMs = 400,
    send = api.issueRefund,
  }: RefundOptions = {},
): Promise<{ refund: Refund; idempotencyKey: string; attemptsUsed: number }> {
  for (let attempt = 1; ; attempt++) {
    try {
      const refund = await send(returnNumber, idempotencyKey, note);
      return { refund, idempotencyKey, attemptsUsed: attempt };
    } catch (error) {
      if (attempt >= attempts || !isRetryable(error)) throw error;
      await new Promise((resolve) => setTimeout(resolve, baseDelayMs * 2 ** (attempt - 1)));
    }
  }
}
