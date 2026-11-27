/* The swap, from the Lightning Address to the on-chain payout, as sequence diagrams.
   Mirrors app/lnurl.py, app/swaps.py and app/worker.py. The README has the same two
   diagrams in mermaid: if the flow changes, update both (and the animation). */
import type { Participant, Step } from "../components/Sequence";

export const PARTICIPANTS: Participant[] = [
  { id: "P", name: "Wallet LN", sub: "de quien paga", tone: "ln" },
  { id: "C", name: "Comunidad", sub: "opcional", tone: "comm" },
  { id: "S", name: "ln2oc", sub: "API + worker" },
  { id: "L", name: "LND", sub: "nodo dedicado", tone: "ln" },
  { id: "B", name: "Bitcoin", sub: "tu cold wallet", tone: "btc" },
];

const START: Step[] = [
  { note: "1. LIGHTNING ADDRESS  bc1q…@ln2oc.com" },
  { from: "C", to: "S", text: "/.well-known/lnurlp/bc1q…?community=nombre", tone: "comm" },
  { from: "P", to: "S", text: "o directo: /.well-known/lnurlp/bc1q…" },
  { from: "S", to: "P", text: "payRequest: callback, min / max, metadata", reply: true },
  { note: "2. INVOICE" },
  { from: "P", to: "S", text: "callback?amount=100.000 sats" },
  { from: "S", to: "S", text: "dirección, monto, comunidad · 700 de comisión" },
  { from: "S", to: "L", text: "AddHoldInvoice(hash del preimage)" },
  { from: "S", to: "P", text: "hold invoice · swap PENDING", reply: true },
  { note: "3. PAGO RETENIDO" },
  { from: "P", to: "L", text: "paga 100.000 sats: el HTLC queda trabado", tone: "ln" },
  { from: "S", to: "L", text: "LookupInvoice (cada 60 s)" },
  { from: "L", to: "S", text: "ACCEPTED, cobrado = monto · INVOICE_HOLD", reply: true },
];

export const SUCCESS: Step[] = [
  ...START,
  { note: "4. PAYOUT, todo en la misma vuelta del worker", tone: "btc" },
  { from: "S", to: "L", text: "¿sin tx en el mempool? saldo − reserva alcanza" },
  { from: "S", to: "L", text: "EstimateFee de la tx real + 20 %" },
  { from: "S", to: "L", text: "SettleInvoice(preimage) → SETTLED", tone: "ln" },
  { from: "S", to: "L", text: "FundPsbt + FinalizePsbt" },
  { from: "S", to: "S", text: "verificar: destino, monto, inputs, minería ≤ cobrada" },
  { from: "S", to: "L", text: "PublishTransaction" },
  { from: "L", to: "B", text: "99.169 sats on-chain · SUCCESS", tone: "btc" },
  { note: "5. COMUNIDAD (si vino con ?community=)", tone: "comm" },
  { from: "S", to: "S", text: "600 para el operador, 100 se le deben a la comunidad" },
  { from: "S", to: "C", text: "el operador liquida a mano, por Lightning", tone: "comm" },
];

export const FAILED: Step[] = [
  ...START,
  { note: "4. SIN SALDO ON-CHAIN: reembolso", tone: "bad" },
  { from: "S", to: "L", text: "saldo − reserva no alcanza (o dirección repetida)" },
  { from: "S", to: "S", text: "swap FAILED (y los que llegaron después)", tone: "bad" },
  { from: "S", to: "L", text: "CancelInvoice → CANCELED", tone: "bad" },
  { from: "L", to: "P", text: "el HTLC se deshace: los 100.000 sats vuelven", reply: true, tone: "ok" },
  { note: "Nada se cobró, nada se firmó, nada salió a la red. La comunidad no cobra." },
];
