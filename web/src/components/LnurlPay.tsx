import { useState } from "react";
import { invoiceAmountMsat } from "../lib/bolt11";
import { fmt } from "../lib/fees";
import { API_URL, useInstanceInfo } from "../lib/info";
import { Qr } from "./Qr";

type State =
  | { s: "idle" }
  | { s: "loading" }
  | { s: "error"; msg: string }
  | { s: "invoice"; pr: string; sat: number };

async function getJson(url: string): Promise<Record<string, unknown>> {
  const r = await fetch(url, { headers: { Accept: "application/json" } });
  const body = await r.json().catch(() => null);
  if (body && body.status === "ERROR") throw new Error(String(body.reason ?? "Error del servicio"));
  if (!r.ok || !body) throw new Error(`El servicio respondió ${r.status}`);
  return body;
}

/** Optional: do what a wallet does with the Lightning Address (LUD-16 → LUD-06) and show the
 * invoice. The address was already validated; the service validates everything again.
 * Before showing the invoice, its network and amount are checked against what was asked:
 * any mismatch is an error, never an invoice on screen. */
export function LnurlPay({ addr }: { addr: string }) {
  const { info } = useInstanceInfo();
  const [amount, setAmount] = useState("");
  const [st, setSt] = useState<State>({ s: "idle" });
  const [copied, setCopied] = useState(false);
  const sat = Number(amount.replace(/\D/g, ""));
  const inRange = sat >= info.min_swap_sat && sat <= info.max_swap_sat;

  async function request() {
    setSt({ s: "loading" });
    try {
      const meta = await getJson(`${API_URL}/.well-known/lnurlp/${addr}`);
      if (meta.tag !== "payRequest" || typeof meta.callback !== "string") throw new Error("Respuesta LNURL inesperada");
      // Only the callback's path and query are used, against the same API this metadata came
      // from (its host is the service's public BASE_URL, which may differ from API_URL in dev).
      // Never ask a third party, and only for this very address.
      const given = new URL(meta.callback);
      if (given.pathname !== "/lnurlp/cb") throw new Error("Callback LNURL inesperado: no se sigue");
      if (given.searchParams.get("btc_address") !== addr) throw new Error("El callback no es para tu dirección");
      const cb = new URL(`${API_URL}/lnurlp/cb${given.search}`, window.location.origin);
      const msat = sat * 1000;
      if (msat < Number(meta.minSendable) || msat > Number(meta.maxSendable)) throw new Error("Monto fuera de rango");
      cb.searchParams.set("amount", String(msat));
      const res = await getJson(cb.toString());
      const pr = res.pr;
      if (typeof pr !== "string") throw new Error("El servicio no devolvió una invoice");
      if (invoiceAmountMsat(pr, info.network) !== BigInt(msat))
        throw new Error("La invoice no coincide con el monto o la red pedidos. No la pagues; avisale al operador.");
      setSt({ s: "invoice", pr, sat });
    } catch (e) {
      setSt({ s: "error", msg: e instanceof Error ? e.message : String(e) });
    }
  }

  async function copy(pr: string) {
    try {
      await navigator.clipboard.writeText(pr);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      /* the invoice text is selectable below */
    }
  }

  if (st.s === "invoice") {
    return (
      <div className="pay pay-invoice">
        <Qr value={st.pr} label={`Invoice Lightning de ${fmt(st.sat)} sats`} />
        <div className="pay-side">
          <span className="k">Pagá {fmt(st.sat)} sats por Lightning</span>
          <p className="pay-dest">
            Destino on-chain: <span className="mono btc">{addr}</span>
          </p>
          <p className="pay-note">
            Revisá que esa sea la dirección de tu cold wallet: el payout va ahí y no se puede deshacer. La invoice es una
            hold invoice: si el nodo no puede pagarte on-chain, se cancela y el pago vuelve a tu wallet.
          </p>
          <div className="pay-actions">
            <a className="btn" href={`lightning:${st.pr}`}>Abrir en mi wallet</a>
            <button type="button" className="btn ghost" onClick={() => copy(st.pr)}>{copied ? "Copiada" : "Copiar invoice"}</button>
            <button type="button" className="btn ghost" onClick={() => setSt({ s: "idle" })}>Otra</button>
          </div>
          <code className="pay-pr">{st.pr}</code>
        </div>
      </div>
    );
  }

  return (
    <div className="pay">
      <label className="k" htmlFor="pay-amt">
        O pagá desde acá
      </label>
      <p className="pay-note">
        Lo mismo que hace tu wallet con la Lightning Address, pero acá: pedís una invoice por el monto y la pagás con
        cualquier wallet Lightning (escaneando el QR).
      </p>
      <div className="pay-row">
        <input
          id="pay-amt"
          inputMode="numeric"
          autoComplete="off"
          placeholder={`${fmt(info.min_swap_sat)} a ${fmt(info.max_swap_sat)} sats`}
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
        />
        <button type="button" className="btn" disabled={!inRange || st.s === "loading" || info.halted} onClick={request}>
          {st.s === "loading" ? "Pidiendo…" : "Generar invoice"}
        </button>
      </div>
      {st.s === "error" && <p className="pay-err" role="alert">{st.msg}</p>}
      {amount && !inRange && <p className="pay-err">Entre {fmt(info.min_swap_sat)} y {fmt(info.max_swap_sat)} sats.</p>}
    </div>
  );
}
