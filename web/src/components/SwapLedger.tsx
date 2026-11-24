import { EXAMPLE_TX_VBYTES, fmt, payoutSat, pct, serviceFeeSat } from "../lib/fees";
import { useInstanceInfo } from "../lib/info";

/** Example swap of `amount` sats: this instance's fee, the current rate, and the size of
 * its last real payout (or a typical one). The real miner fee share is LND's estimate
 * + 20 %, set when the payout is sent. */
export function useSwapExample(amount = 100_000) {
  const { info, live } = useInstanceInfo();
  const rate = info.fee_rate_sat_vb ?? 1;
  const vbytes = info.last_payout_vbytes ?? EXAMPLE_TX_VBYTES;
  const miner = Math.ceil(vbytes * rate * 1.2);
  return {
    info,
    live: live && info.fee_rate_sat_vb !== null,
    amount,
    rate,
    vbytes,
    measured: info.last_payout_vbytes !== null,
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
                Minería, ejemplo ({x.vbytes} vB × {fmt(x.rate)} sat/vB + 20 %)
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
        {x.live ? `Tasa de ahora: ${fmt(x.rate)} sat/vB, según el nodo de esta instancia. ` : "Ejemplo con 1 sat/vB. "}
        {x.measured ? `${x.vbytes} vB es tu parte de lo que pesó el último payout (la tx se comparte con los demás pagos retenidos a la vez). ` : ""}
        La minería se fija al enviar tu pago: la estimación del nodo para la tx real, a la tasa de ese momento, más un 20 %, repartida en partes iguales entre los pagos de esa tx. Sale de tu pago; lo cobrado de más queda para el servicio.
      </p>
    </>
  );
}
