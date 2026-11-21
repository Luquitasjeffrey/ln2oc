import { useEffect, useState } from "react";
import type { Network } from "./address";

/** What GET /api/info returns (app/info.py). */
export type InstanceInfo = {
  service: string;
  version: string;
  commit: string;
  network: Network;
  domain: string;
  swap_fee_rate_bps: number;
  min_swap_sat: number;
  max_swap_sat: number;
  min_payout_sat: number;
  /** Current rate; the miner fee itself is set when each payout is signed. */
  fee_rate_sat_vb: number | null;
  /** Size of the last payout this instance signed, if any. */
  last_payout_vbytes: number | null;
  invoice_poll_interval_seconds: number;
  halted: boolean;
};

/** Shown until /api/info answers, or if it never does: the reference instance's defaults. */
export const DEFAULT_INFO: InstanceInfo = {
  service: "ln2oc",
  version: "",
  commit: "",
  network: "mainnet",
  domain: "ln2oc.com",
  swap_fee_rate_bps: 70,
  min_swap_sat: 1_000,
  max_swap_sat: 1_000_000,
  min_payout_sat: 546,
  fee_rate_sat_vb: null,
  last_payout_vbytes: null,
  invoice_poll_interval_seconds: 60,
  halted: false,
};

export const API_URL: string = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");

export type InfoState = { info: InstanceInfo; live: boolean };

let pending: Promise<InstanceInfo | null> | null = null;

function fetchInfo(): Promise<InstanceInfo | null> {
  pending ??= fetch(`${API_URL}/api/info`, { headers: { Accept: "application/json" } })
    .then((r) => (r.ok ? r.json() : null))
    .catch(() => null);
  return pending;
}

/** Instance parameters from the API; falls back to DEFAULT_INFO (live = false). */
export function useInstanceInfo(): InfoState {
  const [state, setState] = useState<InfoState>({ info: DEFAULT_INFO, live: false });
  useEffect(() => {
    let alive = true;
    fetchInfo().then((data) => {
      if (alive && data) setState({ info: { ...DEFAULT_INFO, ...data }, live: true });
    });
    return () => {
      alive = false;
    };
  }, []);
  return state;
}
