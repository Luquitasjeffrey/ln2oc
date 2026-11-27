/* Same integer math as app/fees.py calculate_gross, minus the miner fee (set at signing). */
export function payoutSat(amountSat: number, feeRateBps: number, minerFeeSat: number): number {
  return Math.floor((amountSat * (10_000 - feeRateBps)) / 10_000) - minerFeeSat;
}

/** Only for examples on the site: a 1-input, 2-output payout (P2TR in, P2WPKH out and change)
 * weighs about this much. Real payouts are priced from the signed tx. */
export const EXAMPLE_TX_VBYTES = 131;

export function serviceFeeSat(amountSat: number, feeRateBps: number): number {
  return amountSat - Math.floor((amountSat * (10_000 - feeRateBps)) / 10_000);
}

const nf = new Intl.NumberFormat("es-AR");
export const fmt = (n: number) => nf.format(n);

/** 70 bps -> "0,7 %" */
export function pct(bps: number): string {
  return `${new Intl.NumberFormat("es-AR", { maximumFractionDigits: 2 }).format(bps / 100)} %`;
}

/** The community's share of the service fee (app/fees.py split_service_fee): floor, the
 * rounding goes to the operator. */
export function communityFeeSat(amountSat: number, communityFeeRateBps: number): number {
  return Math.floor((amountSat * communityFeeRateBps) / 10_000);
}
