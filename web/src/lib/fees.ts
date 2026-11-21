/* Same integer math as app/fees.py: payout = floor(amount * (1 - fee)) - miner fee. */
export function payoutSat(amountSat: number, feeRateBps: number, minerFeeSat: number): number {
  return Math.floor((amountSat * (10_000 - feeRateBps)) / 10_000) - minerFeeSat;
}

export function serviceFeeSat(amountSat: number, feeRateBps: number): number {
  return amountSat - Math.floor((amountSat * (10_000 - feeRateBps)) / 10_000);
}

const nf = new Intl.NumberFormat("es-AR");
export const fmt = (n: number) => nf.format(n);

/** 70 bps -> "0,7 %" */
export function pct(bps: number): string {
  return `${new Intl.NumberFormat("es-AR", { maximumFractionDigits: 2 }).format(bps / 100)} %`;
}
