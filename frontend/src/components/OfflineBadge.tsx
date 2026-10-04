"use client";

import { useEffect, useState } from "react";

import { API_URL } from "@/lib/api";
import type { components } from "@/lib/types";

type Health = components["schemas"]["Health"];

/** "Offline demo" while the API replays its recording instead of calling live services (DEMO_OFFLINE=1). */
export function OfflineBadge() {
  const [offline, setOffline] = useState(false);
  useEffect(() => {
    let active = true;
    fetch(`${API_URL}/api/health`)
      .then((response) => (response.ok ? (response.json() as Promise<Health>) : null))
      .then((health) => {
        if (active && health) setOffline(health.offline);
      })
      .catch(() => {}); // an unreachable API is reported by the report page itself
    return () => {
      active = false;
    };
  }, []);
  if (!offline) return null;
  return (
    <span
      role="status"
      title="Reports replay a recording of earlier live runs; no market, SEC, search or model service is called."
      className="inline-flex items-center gap-1.5 border border-hold px-2 py-0.5 font-mono text-[0.68rem] uppercase tracking-[0.14em] text-hold"
    >
      <span aria-hidden>●</span> Offline demo
    </span>
  );
}
