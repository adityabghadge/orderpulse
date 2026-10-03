import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { OverviewStats } from "../api/types";
import { formatMoney, formatNumber } from "../lib/format";

type Day = OverviewStats["orders_per_day"][number];

function dayLabel(day: string) {
  return new Date(`${day}T00:00:00`).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

function ChartTooltip({ active, payload }: { active?: boolean; payload?: { payload: Day }[] }) {
  const point = payload?.[0]?.payload;
  if (!active || !point) return null;
  return (
    <div className="chart-tip">
      <strong>{dayLabel(point.day)}</strong>
      {formatNumber(point.orders)} orders
      <br />
      {formatMoney(point.revenue_cents)} revenue
    </div>
  );
}

export function OrdersChart({ data }: { data: Day[] }) {
  return (
    <div style={{ width: "100%", height: 240 }}>
      <ResponsiveContainer>
        <BarChart data={data} margin={{ top: 8, right: 4, bottom: 0, left: -12 }} barCategoryGap={2}>
          <CartesianGrid vertical={false} stroke="var(--grid)" />
          <XAxis
            dataKey="day"
            tickFormatter={dayLabel}
            tickLine={false}
            axisLine={{ stroke: "var(--line-strong)" }}
            tick={{ fill: "var(--ink-3)", fontSize: 12 }}
            interval="preserveStartEnd"
            minTickGap={24}
          />
          <YAxis
            allowDecimals={false}
            tickLine={false}
            axisLine={false}
            tick={{ fill: "var(--ink-3)", fontSize: 12 }}
          />
          <Tooltip content={<ChartTooltip />} cursor={{ fill: "var(--panel-sunk)" }} />
          <Bar dataKey="orders" fill="var(--series-1)" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
