import { fmt, payoutSat, pct, serviceFeeSat } from "../lib/fees";
import { useInstanceInfo } from "../lib/info";

/** A swap of `amount` sats with this instance's fee and today's mining estimate. */
export function useSwapExample(amount = 100_000) {
  const { info, live } = useInstanceInfo();
  const rate = info.fee_rate_sat_vb ?? 1;
  const miner = info.miner_fee_sat ?? info.estimated_tx_vbytes * rate;
  return {
    info,
    live: live && info.fee_rate_sat_vb !== null,
    amount,
    rate,
    vbytes: info.estimated_tx_vbytes,
    fee: serviceFeeSat(amount, info.swap_fee_rate_bps),
    feePct: pct(info.swap_fee_rate_bps),
    miner,
    payout: payoutSat(amount, info.swap_fee_rate_bps, miner),
  };
}

export function SwapLedger({ amount = 100_000 }: { amount?: number }) {
  const x = useSwapExample(amount);
  return (
    <>
      <div className="table-wrap">
        <table className="ledger">
          <thead>
            <tr>
              <th>Concepto</th>
              <th className="r">sats</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Pagás por Lightning</td>
              <td className="r ln">{fmt(x.amount)}</td>
            </tr>
            <tr>
              <td>Comisión del servicio ({x.feePct})</td>
              <td className="r">−{fmt(x.fee)}</td>
            </tr>
            <tr>
              <td>
                Minería estimada ({x.vbytes} vB × {fmt(x.rate)} sat/vB)
              </td>
              <td className="r">−{fmt(x.miner)}</td>
            </tr>
          </tbody>
          <tfoot>
            <tr>
              <td>Llega a tu cold wallet (aprox.)</td>
              <td className="r btc">{fmt(x.payout)}</td>
            </tr>
          </tfoot>
        </table>
      </div>
      <p style={{ color: "var(--muted)", fontSize: "var(--step--1)" }}>
        {x.live
          ? `Con la minería de ahora, ${fmt(x.rate)} sat/vB, según el nodo de esta instancia.`
          : "Ejemplo con 1 sat/vB de minería."}{" "}
        Es una estimación con 160 vB: se descuenta la minería real de tu tx, a la tasa del momento de pedir la invoice. Una tx típica pesa unos 131 vB, así que suele llegar un poco más. El servicio se queda solo con la comisión.
      </p>
    </>
  );
}
