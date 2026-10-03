import { ApiError } from "../api/client";
import type { Refund } from "../api/types";
import { isRetryable, refundWithRetry } from "./refund";

const refund: Refund = {
  id: 1,
  return_number: "RT-500001",
  amount_cents: 5900,
  currency: "USD",
  status: "succeeded",
  provider_reference: "re_test",
  created_at: "2026-10-02T12:00:00Z",
};

describe("isRetryable", () => {
  it("retries network failures and gateway errors only", () => {
    expect(isRetryable(new TypeError("Failed to fetch"))).toBe(true);
    expect(isRetryable(new ApiError(502, "payment_provider_error", "timeout"))).toBe(true);
    expect(isRetryable(new ApiError(503, "unavailable", "down"))).toBe(true);
    expect(isRetryable(new ApiError(409, "conflict", "already refunded"))).toBe(false);
    expect(isRetryable(new ApiError(422, "validation_error", "bad"))).toBe(false);
  });
});

describe("refundWithRetry", () => {
  it("reuses the same idempotency key on every retry", async () => {
    const send = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockRejectedValueOnce(new ApiError(502, "payment_provider_error", "timeout"))
      .mockResolvedValueOnce(refund);

    const result = await refundWithRetry("RT-500001", { send, baseDelayMs: 0 });

    expect(result.refund).toEqual(refund);
    expect(result.attemptsUsed).toBe(3);
    const keys = send.mock.calls.map((call) => call[1]);
    expect(new Set(keys).size).toBe(1);
    expect(keys[0]).toBe(result.idempotencyKey);
  });

  it("does not retry business errors", async () => {
    const send = vi.fn().mockRejectedValue(new ApiError(409, "conflict", "already refunded"));
    await expect(refundWithRetry("RT-500001", { send, baseDelayMs: 0 })).rejects.toThrow(
      "already refunded",
    );
    expect(send).toHaveBeenCalledTimes(1);
  });

  it("gives up after the last attempt", async () => {
    const send = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(
      refundWithRetry("RT-500001", { send, attempts: 3, baseDelayMs: 0 }),
    ).rejects.toThrow("Failed to fetch");
    expect(send).toHaveBeenCalledTimes(3);
  });

  it("uses a fresh key for each new refund attempt", async () => {
    const send = vi.fn().mockResolvedValue(refund);
    const first = await refundWithRetry("RT-500001", { send });
    const second = await refundWithRetry("RT-500001", { send });
    expect(first.idempotencyKey).not.toBe(second.idempotencyKey);
  });
});
