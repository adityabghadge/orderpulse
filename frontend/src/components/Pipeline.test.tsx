import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import type { OverviewStats } from "../api/types";
import { Pipeline } from "./Pipeline";
import { OrderStatusPill, ReturnStatusPill } from "./StatusPill";

const stats = {
  pipeline: [
    { status: "placed", count: 10 },
    { status: "packed", count: 30 },
    { status: "shipped", count: 50 },
    { status: "out_for_delivery", count: 10 },
  ],
  delivered_last_7d: 400,
  cancelled_last_7d: 12,
} as OverviewStats;

function CurrentUrl() {
  const location = useLocation();
  return <output data-testid="url">{location.pathname + location.search}</output>;
}

describe("Pipeline", () => {
  it("shows each stage with its share of in-flight orders", () => {
    render(
      <MemoryRouter>
        <Pipeline stats={stats} />
      </MemoryRouter>,
    );
    expect(screen.getByRole("heading", { name: "100 orders on the way to customers" }));
    expect(screen.getByRole("button", { name: "Shipped: 50 orders" })).toHaveTextContent(
      "50% of in-flight",
    );
    expect(screen.getByText("delivered in the last 7 days").parentElement).toHaveTextContent(
      "400",
    );
  });

  it("opens the orders list filtered to the selected stage", async () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<Pipeline stats={stats} />} />
          <Route path="/orders" element={<CurrentUrl />} />
        </Routes>
      </MemoryRouter>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Packed: 30 orders" }));
    expect(screen.getByTestId("url")).toHaveTextContent("/orders?status=packed");
  });
});

describe("status pills", () => {
  it("use plain-language labels", () => {
    render(
      <>
        <OrderStatusPill status="out_for_delivery" />
        <ReturnStatusPill status="received" />
      </>,
    );
    expect(screen.getByText("Out for delivery")).toBeInTheDocument();
    expect(screen.getByText("Ready to refund")).toBeInTheDocument();
  });
});
