import { formatAge, formatCompactMoney, formatMoney, NEXT_ORDER_STATUS } from "./format";

describe("money", () => {
  it("formats cents as dollars", () => {
    expect(formatMoney(13600)).toBe("$136.00");
    expect(formatMoney(5)).toBe("$0.05");
    expect(formatCompactMoney(2_789_813)).toBe("$27.9K");
  });
});

describe("formatAge", () => {
  const now = new Date("2026-10-02T12:00:00Z");
  it.each([
    ["2026-10-02T11:59:45Z", "just now"],
    ["2026-10-02T11:55:00Z", "5 min ago"],
    ["2026-10-02T09:00:00Z", "3 h ago"],
    ["2026-10-01T12:00:00Z", "1 day ago"],
    ["2026-09-28T12:00:00Z", "4 days ago"],
  ])("%s -> %s", (iso, expected) => {
    expect(formatAge(iso, now)).toBe(expected);
  });
});

describe("order lifecycle", () => {
  it("mirrors the backend's next-step rules", () => {
    expect(NEXT_ORDER_STATUS).toEqual({
      placed: "packed",
      packed: "shipped",
      shipped: "out_for_delivery",
      out_for_delivery: "delivered",
    });
  });
});
