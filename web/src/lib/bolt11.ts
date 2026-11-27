/* Just enough of BOLT 11 to cross-check the invoice the service hands back before showing
   it: the network prefix and the amount in the human-readable part. The wallet decodes the
   rest. Anything that does not parse is rejected (the page shows an error, never the
   invoice). */
import type { Network } from "./address";

const PREFIX: Record<Network, string> = { mainnet: "lnbc", testnet: "lntb", testnet4: "lntb", regtest: "lnbcrt" };
// Multipliers in pico-bitcoin (10^-12 BTC). 1 msat = 10^-11 BTC = 10 pBTC.
const MULT: Record<string, bigint> = { m: 1_000_000_000n, u: 1_000_000n, n: 1_000n, p: 1n };

/** Amount in msat encoded in the invoice, or null if it is not a valid one for `network`. */
export function invoiceAmountMsat(pr: string, network: Network): bigint | null {
  const s = pr.trim().toLowerCase();
  const sep = s.lastIndexOf("1");
  if (sep < 0) return null;
  const hrp = s.slice(0, sep);
  const prefix = PREFIX[network];
  if (!hrp.startsWith(prefix)) return null;
  // regtest's "lnbcrt" also starts with "lnbc": the amount regex below rejects "rt…".
  const amt = hrp.slice(prefix.length);
  const m = /^([1-9][0-9]*)([munp])$/.exec(amt);
  if (!m) return null;
  const pico = BigInt(m[1]) * MULT[m[2]];
  if (pico % 10n !== 0n) return null;
  return pico / 10n;
}
