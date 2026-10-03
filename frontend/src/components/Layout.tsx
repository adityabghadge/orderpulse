import { useQuery } from "@tanstack/react-query";
import { NavLink, Outlet } from "react-router-dom";

import { useOverview } from "../api/hooks";

function Logo() {
  return (
    <svg width="26" height="26" viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="7" fill="var(--accent)" />
      <path
        d="M5 17h5l3-7 5 13 3-6h6"
        fill="none"
        stroke="var(--panel)"
        strokeWidth="2.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function useApiHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: async () => {
      const response = await fetch("/health");
      if (!response.ok) throw new Error("unhealthy");
      return response.json();
    },
    refetchInterval: 15_000,
    retry: false,
  });
}

export function Layout() {
  const overview = useOverview();
  const health = useApiHealth();
  const needsReview = overview.data?.returns_by_status.requested ?? 0;

  return (
    <div className="shell">
      <aside className="sidebar">
        <NavLink to="/" className="brand" end>
          <Logo />
          OrderPulse
        </NavLink>
        <nav className="nav" aria-label="Main">
          <NavLink to="/" end>
            Overview
          </NavLink>
          <NavLink to="/orders">Orders</NavLink>
          <NavLink to="/returns">
            Returns
            {needsReview > 0 && (
              <span className="count" aria-label={`${needsReview} need review`}>
                {needsReview}
              </span>
            )}
          </NavLink>
        </nav>
        <div className="sidebar-foot">
          {health.isError ? (
            <span className="health down">API unreachable</span>
          ) : (
            <span className="health">API connected</span>
          )}
        </div>
      </aside>
      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}
