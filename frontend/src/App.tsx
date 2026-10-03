import { lazy, Suspense, type ReactNode } from "react";
import { Link, Route, Routes } from "react-router-dom";

import { Layout } from "./components/Layout";
import { EmptyState } from "./components/States";

// Each page is downloaded only when first visited, keeping the initial load small.
const OverviewPage = lazy(() =>
  import("./pages/OverviewPage").then((m) => ({ default: m.OverviewPage })),
);
const OrdersPage = lazy(() => import("./pages/OrdersPage").then((m) => ({ default: m.OrdersPage })));
const OrderDetailPage = lazy(() =>
  import("./pages/OrderDetailPage").then((m) => ({ default: m.OrderDetailPage })),
);
const ReturnsPage = lazy(() =>
  import("./pages/ReturnsPage").then((m) => ({ default: m.ReturnsPage })),
);

const page = (element: ReactNode) => <Suspense fallback={null}>{element}</Suspense>;

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={page(<OverviewPage />)} />
        <Route path="orders" element={page(<OrdersPage />)} />
        <Route path="orders/:orderNumber" element={page(<OrderDetailPage />)} />
        <Route path="returns" element={page(<ReturnsPage />)} />
        <Route
          path="*"
          element={
            <section className="panel">
              <EmptyState title="This page doesn't exist">
                <Link to="/">Go to the overview</Link>
              </EmptyState>
            </section>
          }
        />
      </Route>
    </Routes>
  );
}
