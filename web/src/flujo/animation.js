/* The swap animation, ported as-is from the documentation artifact (flujo.html).
   Imperative canvas code: mounted by <FlowAnimation /> on its root element.
   Returns a cleanup function that stops the loop and removes global listeners. */
// @ts-nocheck
export function mountFlow(root, initial = "user") {
  let disposed = false;

  const C = {
    bg: "#0d0f16", ink: "#ece9e1", dim: "#8b8f98", faint: "#3a3e45",
    blue: "#58c4dd", yellow: "#f4d345", green: "#83c167", red: "#fc6255", gold: "#f0ac5f",
  };
  const SERIF = 'ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif';
  const MONO = 'ui-monospace, "SFMono-Regular", Menlo, Consolas, "Liberation Mono", monospace';
  const W = 1280, H = 720;

  const cv = root.querySelector("[data-flow=canvas]");
  const ctx = cv.getContext("2d");

  // ---------------------------------------------------------------- scenarios
  const SCEN = {
    user: {
      name: "Lo que ve el usuario",
      scenes: [
        { k: "u-addr", a: 0,  b: 6,  step: "Paso 1", title: "Tu Lightning Address",
          cap: "Copiás una dirección de tu cold wallet y le sumás @ln2oc.com. Esa es tu Lightning Address: sin registro, sin cuenta." },
        { k: "u-pay",  a: 6,  b: 14, step: "Paso 2", title: "Pagás desde tu wallet",
          cap: "Pagás desde cualquier wallet Lightning: Wallet of Satoshi, Phoenix, la que uses. Los sats aterrizan on-chain en tu cold wallet." },
        { k: "u-p2p",  a: 14, b: 22, step: "O bien", title: "Cobrás un trade P2P",
          cap: "Comprás sats en un exchange P2P, por ejemplo Mostro, y ponés tu Lightning Address de ln2oc como destino. Cuando el vendedor libera, van directo a frío." },
        { k: "u-fail", a: 22, b: 30, step: "Si falla", title: "Tus sats no se mueven",
          cap: "Si el nodo de ln2oc no tiene fondos on-chain, el pago falla y tus sats nunca salen de tu wallet." },
        { k: "u-end",  a: 30, b: 35, step: "", title: "Resumen" },
      ],
      chips: [], chipAt: [],
    },
    community: {
      name: "Comunidades",
      scenes: [
        { k: "c-hook",  a: 0,  b: 7,  step: "Paso 1", title: "Tu servicio suma un parámetro",
          cap: "Tu exchange, wallet o sistema de pagos arma la Lightning Address del usuario y, al pedir la invoice, agrega ?community=tu-comunidad. Nada más cambia." },
        { k: "c-pay",   a: 7,  b: 14, step: "Paso 2", title: "Tu usuario retira on-chain",
          cap: "El usuario paga por Lightning y sus sats llegan on-chain a su cold wallet. Paga exactamente lo mismo que sin comunidad." },
        { k: "c-split", a: 14, b: 21, step: "Paso 3", title: "La comisión se reparte",
          cap: "De la comisión de 0,7 %, el 0,1 % es de tu comunidad. En un retiro de 100.000 sats: 600 para el operador y 100 para vos." },
        { k: "c-sum",   a: 21, b: 28, step: "Paso 4", title: "Cada retiro suma",
          cap: "Cada swap exitoso que llega con tu parámetro suma a lo que se te debe. No hay saldo guardado: sale de los swaps exitosos menos lo que ya se te pagó." },
        { k: "c-paid",  a: 28, b: 34, step: "Paso 5", title: "El operador te paga",
          cap: "El operador te liquida por Lightning, a una invoice o a tu Lightning Address, y registra el pago. El contador vuelve a cero." },
        { k: "c-end",   a: 34, b: 39, step: "", title: "Resumen" },
      ],
      chips: [], chipAt: [],
    },
    ok: {
      name: "Swap exitoso",
      scenes: [
        { k: "title",   a: 0,    b: 3,    step: "",              title: "Inicio" },
        { k: "actors",  a: 3,    b: 6,    step: "Los actores",   title: "Los actores",
          cap: "Tres lugares: la billetera Lightning de quien paga, un nodo LN dedicado solo a ln2oc y tu cold wallet." },
        { k: "invoice", a: 6,    b: 11,   step: "Paso 1",        title: "Pedir la invoice",
          cap: "Tu wallet pide la invoice. Si el pago viene por una comunidad, su servicio agrega ?community=<handle> al pedido, y nada más cambia. El nodo genera un secreto, el preimage, y emite una hold invoice atada a su hash." },
        { k: "pay",     a: 11,   b: 16.5, step: "Paso 2",        title: "El pago queda retenido",
          cap: "Pagás. El HTLC llega y la invoice pasa a ACCEPTED: la plata está retenida, nadie la cobró todavía. El worker lo ve en su próxima consulta de invoices pendientes (LookupInvoice) y el swap pasa a INVOICE_HOLD." },
        { k: "check",   a: 16.5, b: 20,   step: "Paso 3",        title: "Chequear el saldo",
          cap: "Si la wallet on-chain tiene alguna tx sin confirmar, el worker no hace nada y espera. Con la wallet quieta, todos los pagos retenidos van juntos en una tx, del más viejo al más nuevo, mientras entren en el saldo (menos una reserva que nunca se paga, para que el cambio no quede en dust). La minería es la estimación de LND + 20 %, en partes iguales, y no puede dejar tu payout en dust. No se firma nada todavía." },
        { k: "settle",  a: 20,   b: 24.5, step: "Paso 4",        title: "Cobrar con el preimage",
          cap: "El nodo revela el preimage y cobra: LND tiene que confirmar SETTLED al instante. Recién ahora la plata Lightning es del operador." },
        { k: "fund",    a: 24.5, b: 30.5, step: "Paso 5",        title: "Armar y firmar",
          cap: "En la misma vuelta, FundPsbt arma la tx con tu payout ya neto de minería (y los de los demás pagos retenidos) y FinalizePsbt la firma. La tx se verifica: cada destino una vez con su monto y la minería real nunca por encima de lo cobrado." },
        { k: "publish", a: 30.5, b: 36,   step: "Paso 6",        title: "Publicar y confirmar",
          cap: "Se publica esa tx y el swap pasa a SUCCESS. Si algo falla desde el cobro, el servicio se frena y lo revisa una persona: nunca se reintenta a ciegas. Entra en un bloque y los sats son tuyos, con tus llaves." },
        { k: "ledger",  a: 36,   b: 42,   step: "Balance",       title: "Quién terminó con qué",
          cap: "Nadie creó sats: cambiaron de capa. Vos tenés tus sats en frío. De los 700 de comisión, 600 son del operador y 100 de la comunidad por la que llegó el pago, que el operador le liquida a mano." },
      ],
      chips: ["PENDING", "INVOICE_HOLD", "SUCCESS"],
      chipAt: [[9.5, 0], [14, 1], [33.3, 2]],
      inv: ["OPEN", "ACCEPTED", "SETTLED"], invAt: [[9.5, 0], [14, 1], [22.5, 2]],
    },
    fail: {
      name: "Sin saldo on-chain",
      scenes: [
        { k: "title",   a: 0,    b: 3,    step: "",              title: "Inicio" },
        { k: "actors",  a: 3,    b: 6,    step: "Los actores",   title: "Los actores",
          cap: "Mismo escenario, pero esta vez la wallet on-chain del nodo no alcanza para cubrir el payout." },
        { k: "invoice", a: 6,    b: 11,   step: "Paso 1",        title: "Pedir la invoice",
          cap: "Tu wallet pide la invoice. Emitirla no reserva liquidez: el compromiso recién se toma cuando llega el pago." },
        { k: "pay",     a: 11,   b: 16.5, step: "Paso 2",        title: "El pago queda retenido",
          cap: "Pagás. El HTLC llega y la invoice pasa a ACCEPTED: la plata está retenida, nadie la cobró todavía." },
        { k: "fail",    a: 16.5, b: 21.5, step: "Paso 3",        title: "No hay saldo",
          cap: "Con la invoice en ACCEPTED, el worker mira el saldo on-chain y no alcanza: tu pago y los que llegaron después se cancelan. No se cobró, no se firmó y no salió nada a la red." },
        { k: "refund",  a: 21.5, b: 26,   step: "Paso 4",        title: "Cancelar y reembolsar",
          cap: "El nodo cancela la hold invoice y pasa a CANCELED. El HTLC se deshace: los sats nunca se cobraron y siguen en la wallet del pagador." },
        { k: "ledger",  a: 26,   b: 31,   step: "Balance",       title: "Quién terminó con qué",
          cap: "Nadie pierde nada. Ese es el trato de la hold invoice: sin fondos on-chain, no hay cobro." },
      ],
      chips: ["PENDING", "INVOICE_HOLD", "FAILED"],
      chipAt: [[9.5, 0], [14, 1], [22.85, 2]],
      inv: ["OPEN", "ACCEPTED", "CANCELED"], invAt: [[9.5, 0], [14, 1], [22.85, 2]],
    },
  };

  let scen = "user";
  let t = 0, playing = true, last = null, raf = null;
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;

  const total = () => SCEN[scen].scenes.at(-1).b;
  const scene = (k) => SCEN[scen].scenes.find((s) => s.k === k);
  const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
  const ease = (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
  const lerp = (a, b, x) => a + (b - a) * x;
  // progress of a sub-window [f0, f1] (fractions) of scene k, eased
  function P(k, f0 = 0, f1 = 1) {
    const s = scene(k);
    if (!s) return 0;
    const a = s.a + (s.b - s.a) * f0, b = s.a + (s.b - s.a) * f1;
    return ease(clamp((t - a) / (b - a)));
  }
  const after = (k, f = 0) => { const s = scene(k); return s ? t >= s.a + (s.b - s.a) * f : false; };
  const current = () => SCEN[scen].scenes.findLast((s) => t >= s.a) || SCEN[scen].scenes[0];

  // ---------------------------------------------------------------- primitives
  function rr(x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
  }
  function drawBox(b, p, color = C.ink) {
    if (p <= 0) return;
    rr(b.x, b.y, b.w, b.h, 14);
    const per = 2 * (b.w + b.h);
    ctx.save(); ctx.strokeStyle = color; ctx.lineWidth = 2;
    ctx.setLineDash([per * p, per]); ctx.stroke(); ctx.restore();
  }
  function text(s, x, y, { font = `24px ${SERIF}`, color = C.ink, align = "left", alpha = 1, write = 1 } = {}) {
    if (alpha <= 0 || write <= 0) return;
    ctx.save(); ctx.globalAlpha *= Math.min(1, alpha); ctx.font = font; ctx.fillStyle = color; ctx.textAlign = align; ctx.textBaseline = "alphabetic";
    if (write < 1) {
      const w = ctx.measureText(s).width;
      const x0 = align === "center" ? x - w / 2 : align === "right" ? x - w : x;
      ctx.beginPath(); ctx.rect(x0 - 2, y - 80, (w + 4) * write, 120); ctx.clip();
    }
    ctx.fillText(s, x, y); ctx.restore();
  }
  function wrap(s, maxW, font) {
    ctx.font = font; const words = s.split(" "); const lines = []; let line = "";
    for (const w of words) { const test = line ? line + " " + w : w; if (ctx.measureText(test).width > maxW && line) { lines.push(line); line = w; } else line = test; }
    if (line) lines.push(line); return lines;
  }
  function coin(x, y, color, r = 10, alpha = 1) {
    if (alpha <= 0) return;
    ctx.save(); ctx.globalAlpha *= alpha;
    ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fillStyle = color; ctx.fill();
    ctx.lineWidth = 2; ctx.strokeStyle = "rgba(0,0,0,0.35)"; ctx.stroke();
    ctx.beginPath(); ctx.arc(x, y, r * 0.55, 0, Math.PI * 2); ctx.strokeStyle = "rgba(0,0,0,0.25)"; ctx.lineWidth = 1.5; ctx.stroke();
    ctx.restore();
  }
  function arrow(x1, y1, x2, y2, p, color, width = 2) {
    if (p <= 0) return;
    const x = lerp(x1, x2, p), y = lerp(y1, y2, p);
    ctx.save(); ctx.strokeStyle = color; ctx.fillStyle = color; ctx.lineWidth = width;
    ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x, y); ctx.stroke();
    const ang = Math.atan2(y2 - y1, x2 - x1);
    ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x - 12 * Math.cos(ang - 0.4), y - 12 * Math.sin(ang - 0.4));
    ctx.lineTo(x - 12 * Math.cos(ang + 0.4), y - 12 * Math.sin(ang + 0.4)); ctx.closePath(); ctx.fill();
    ctx.restore();
  }
  function lock(x, y, open, color, alpha = 1) {
    if (alpha <= 0) return;
    ctx.save(); ctx.globalAlpha *= alpha; ctx.strokeStyle = color; ctx.fillStyle = color; ctx.lineWidth = 3.5;
    ctx.save(); ctx.translate(x + 9 * open, y - 14 * open); ctx.rotate(-0.5 * open);
    ctx.beginPath(); ctx.arc(x - x, y - 8 - y, 10, Math.PI, 0); ctx.lineTo(10, 2 - 0); ctx.moveTo(-10, -8); ctx.lineTo(-10, 2); ctx.stroke();
    ctx.restore();
    rr(x - 15, y - 2, 30, 24, 4); ctx.fill();
    ctx.fillStyle = C.bg; ctx.beginPath(); ctx.arc(x, y + 9, 3.5, 0, Math.PI * 2); ctx.fill();
    ctx.restore();
  }
  function key(x, y, color, alpha = 1) {
    if (alpha <= 0) return;
    ctx.save(); ctx.globalAlpha *= alpha; ctx.strokeStyle = color; ctx.lineWidth = 3.5;
    ctx.beginPath(); ctx.arc(x - 14, y, 8, 0, Math.PI * 2); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(x - 6, y); ctx.lineTo(x + 18, y); ctx.moveTo(x + 10, y); ctx.lineTo(x + 10, y + 8); ctx.moveTo(x + 17, y); ctx.lineTo(x + 17, y + 6); ctx.stroke();
    ctx.restore();
  }
  function pulse(x, y, p, color) {
    if (p <= 0 || p >= 1) return;
    ctx.save(); ctx.globalAlpha = 1 - p; ctx.strokeStyle = color; ctx.lineWidth = 2.5;
    ctx.beginPath(); ctx.arc(x, y, 10 + 40 * p, 0, Math.PI * 2); ctx.stroke(); ctx.restore();
  }
  function stamp(s, x, y, color, alpha) {
    if (alpha <= 0) return;
    ctx.save(); ctx.globalAlpha *= alpha; ctx.translate(x, y); ctx.rotate(-0.035);
    ctx.font = `600 15px ${MONO}`; const w = ctx.measureText(s).width + 24;
    rr(-w / 2, -16, w, 30, 5); ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.stroke();
    ctx.fillStyle = color; ctx.textAlign = "center"; ctx.fillText(s, 0, 5); ctx.restore();
  }

  // ---------------------------------------------------------------- layout
  const PAYER = { x: 70, y: 130, w: 260, h: 210 };
  const NODE = { x: 470, y: 110, w: 340, h: 280 };
  const COLD = { x: 950, y: 130, w: 260, h: 210 };
  const CH_Y = 232;                 // lightning channel line
  const LOCK = { x: 448, y: CH_Y - 10 };
  const N = 5;                      // coins representing 100.000 sats
  const payerCoin = (i) => ({ x: 132 + i * 34, y: 292 });
  const heldCoin = (i) => ({ x: 412 - i * 16, y: CH_Y });
  const poolCoin = (i) => ({ x: 560 + i * 22, y: 238 });
  const coldCoin = (i) => ({ x: 1012 + i * 30, y: 292 });
  const UTXOS = [{ x: 572, l: "0,02 BTC" }, { x: 640, l: "0,015 BTC" }, { x: 708, l: "0,01 BTC" }];
  const UTXO_Y = 336;

  // ---------------------------------------------------------------- frame
  function frame() {
    ctx.setTransform(cv.width / W, 0, 0, cv.height / H, 0, 0);
    ctx.fillStyle = C.bg; ctx.fillRect(0, 0, W, H);
    if (scen === "user") { frameUser(); return; }
    if (scen === "community") { frameCommunity(); return; }
    const fail = scen === "fail";

    // Title card
    const pt = scene("title");
    if (t < pt.b) {
      const fade = 1 - clamp((t - (pt.b - 0.6)) / 0.6);
      text("Un swap, paso a paso", W / 2, 330, { font: `600 58px ${SERIF}`, align: "center", write: P("title", 0, 0.55), alpha: fade });
      text(fail ? "y qué pasa cuando el nodo no tiene fondos" : "de Lightning a tu cold wallet", W / 2, 392,
        { font: `italic 28px ${SERIF}`, color: fail ? C.red : C.yellow, align: "center", alpha: P("title", 0.45, 0.8) * fade });
      return;
    }

    const show = P("actors", 0, 0.6), labels = P("actors", 0.3, 0.9);
    // step label
    const cur = current();
    if (cur.step) {
      text(cur.step, 70, 74, { font: `600 15px ${MONO}`, color: C.dim });
      text(cur.title, 70 + (cur.step.length + 2) * 9.6, 74, { font: `italic 24px ${SERIF}`, color: C.ink });
    }
    text(SCEN[scen].name, W - 70, 74, { font: `15px ${MONO}`, color: fail ? C.red : C.dim, align: "right" });

    // actors
    drawBox(PAYER, show); drawBox(NODE, show); drawBox(COLD, show);
    text("Billetera LN", PAYER.x + PAYER.w / 2, PAYER.y + 46, { font: `600 26px ${SERIF}`, align: "center", alpha: labels });
    text("del pagador", PAYER.x + PAYER.w / 2, PAYER.y + 74, { font: `italic 19px ${SERIF}`, color: C.dim, align: "center", alpha: labels });
    text("Nodo LN dedicado", NODE.x + NODE.w / 2, NODE.y + 40, { font: `600 26px ${SERIF}`, align: "center", alpha: labels });
    text("solo ln2oc · poca plata", NODE.x + NODE.w / 2, NODE.y + 66, { font: `15px ${MONO}`, color: C.dim, align: "center", alpha: labels });
    text("Tu cold wallet", COLD.x + COLD.w / 2, COLD.y + 46, { font: `600 26px ${SERIF}`, align: "center", alpha: labels });
    text("tus llaves, offline", COLD.x + COLD.w / 2, COLD.y + 74, { font: `italic 19px ${SERIF}`, color: C.dim, align: "center", alpha: labels });
    // node interior
    ctx.save(); ctx.globalAlpha = labels; ctx.strokeStyle = C.faint; ctx.lineWidth = 1.5; ctx.setLineDash([5, 6]);
    ctx.beginPath(); ctx.moveTo(NODE.x + 14, 268); ctx.lineTo(NODE.x + NODE.w - 14, 268); ctx.stroke(); ctx.restore();
    text("lightning", NODE.x + 18, 258, { font: `13px ${MONO}`, color: C.yellow, alpha: labels * 0.8 });
    text("on-chain", NODE.x + 18, 290, { font: `13px ${MONO}`, color: C.gold, alpha: labels * 0.8 });
    // channel
    ctx.save(); ctx.globalAlpha = show; ctx.strokeStyle = C.faint; ctx.lineWidth = 3;
    ctx.beginPath(); ctx.moveTo(PAYER.x + PAYER.w, CH_Y); ctx.lineTo(NODE.x, CH_Y); ctx.stroke(); ctx.restore();
    text("canal", (PAYER.x + PAYER.w + NODE.x) / 2, CH_Y + 26, { font: `13px ${MONO}`, color: C.dim, align: "center", alpha: labels * (1 - P("pay", 0.3, 0.5)) });

    // UTXOs (operator on-chain funds)
    UTXOS.forEach((u, i) => {
      const small = fail;
      const a = labels * (fail ? 0.55 : 1);
      coin(u.x, UTXO_Y, C.gold, small ? 9 : 17, a);
      text(fail ? (i === 0 ? "0,0004 BTC" : "") : u.l, u.x, UTXO_Y + 36, { font: `12px ${MONO}`, color: C.dim, align: "center", alpha: a });
    });
    if (fail) { /* only one dusty UTXO */ }

    // ---------------- Paso 1: invoice
    const req = P("invoice", 0, 0.3);
    arrow(PAYER.x + PAYER.w, 168, NODE.x - 6, 168, req, C.blue);
    text("GET /lnurlp/cb", (PAYER.x + PAYER.w + NODE.x) / 2, 156, { font: `13px ${MONO}`, color: C.blue, align: "center", alpha: req });
    // preimage inside node
    const kp = P("invoice", 0.25, 0.5);
    const settleMove = scen === "ok" ? P("settle", 0, 0.45) : 0;
    const kx = lerp(758, LOCK.x + 22, settleMove), ky = lerp(224, LOCK.y + 34, settleMove);
    const keyAlpha = kp * (scen === "ok" ? 1 - P("settle", 0.55, 0.75) : 1);
    key(kx, ky, C.yellow, keyAlpha);
    text("preimage", 758, 252, { font: `13px ${MONO}`, color: C.yellow, align: "center", alpha: kp * (1 - settleMove) });
    // invoice card travelling to payer
    const ic = P("invoice", 0.45, 0.85);
    if (after("invoice", 0.45)) {
      const cx = lerp(NODE.x + 60, PAYER.x + 15, ic), cy = lerp(300, 404, ic);
      ctx.save(); ctx.globalAlpha = Math.min(1, ic * 3);
      rr(cx, cy, 230, 92, 8); ctx.fillStyle = "#16181b"; ctx.fill(); ctx.strokeStyle = C.yellow; ctx.lineWidth = 1.5; ctx.stroke();
      ctx.restore();
      text("hold invoice", cx + 14, cy + 26, { font: `600 14px ${MONO}`, color: C.yellow, alpha: Math.min(1, ic * 3) });
      text("100.000 sats", cx + 14, cy + 52, { font: `20px ${SERIF}`, alpha: Math.min(1, ic * 3) });
      text("H = SHA256(preimage)", cx + 14, cy + 76, { font: `13px ${MONO}`, color: C.dim, alpha: Math.min(1, ic * 3) });
    }

    // ---------------- coins: payer balance, flight, hold, settle / refund
    const fly = P("pay", 0, 0.45);
    const toPool = scen === "ok" ? P("settle", 0.5, 0.95) : 0;
    const back = fail ? P("refund", 0.3, 0.85) : 0;
    for (let i = 0; i < N; i++) {
      const s = payerCoin(i), h = heldCoin(i);
      const stag = clamp(fly * 1.6 - i * 0.15);
      let x = lerp(s.x, h.x, stag), y = lerp(s.y, h.y, stag);
      // little arc while flying
      y -= Math.sin(stag * Math.PI) * 26;
      if (toPool > 0) { const q = clamp(toPool * 1.5 - i * 0.12); const pc = poolCoin(i); x = lerp(h.x, pc.x, q); y = lerp(h.y, pc.y, q) - Math.sin(q * Math.PI) * 30; }
      if (back > 0) { const q = clamp(back * 1.5 - i * 0.12); x = lerp(h.x, s.x, q); y = lerp(h.y, s.y, q) - Math.sin(q * Math.PI) * 30; }
      coin(x, y, C.yellow, 10, labels);
    }
    text("100.000 sats", PAYER.x + PAYER.w / 2, 326, { font: `16px ${MONO}`, color: C.dim, align: "center", alpha: labels * (1 - fly) + back });

    // HTLC lock
    const lockIn = P("pay", 0.4, 0.6);
    const lockOpen = scen === "ok" ? P("settle", 0.4, 0.55) : 0;
    const lockFade = scen === "ok" ? 1 - P("settle", 0.6, 0.8) : 1 - P("refund", 0.75, 0.95);
    const lockColor = fail && after("refund", 0) ? C.red : C.ink;
    lock(LOCK.x, LOCK.y - 2, lockOpen, lockColor, lockIn * lockFade);
    const canceled = fail && after("refund", 0.05);
    text(canceled ? "HTLC" : "HTLC retenido", 400, 274, { font: `12px ${MONO}`, color: canceled ? C.red : C.ink, align: "center", alpha: lockIn * lockFade });
    text(canceled ? "cancelado" : "ACCEPTED", 400, 290, { font: `600 12px ${MONO}`, color: canceled ? C.red : C.yellow, align: "center", alpha: lockIn * lockFade });
    // poll pulse: the worker looks the invoice up
    const sub = P("pay", 0.62, 0.95);
    if (sub > 0) {
      pulse(LOCK.x, LOCK.y + 8, clamp(sub * 1.4), C.blue);
      arrow(LOCK.x + 26, 196, 690, 196, P("pay", 0.62, 0.85), C.blue, 1.5);
      text("LookupInvoice: el worker lo ve", 600, 216, { font: `12px ${MONO}`, color: C.blue, align: "center", alpha: sub });
      text("worker", 698, 201, { font: `600 14px ${MONO}`, color: C.blue, alpha: sub });
    }
    text("+100.000 sats", 604, 263, { font: `14px ${MONO}`, color: C.yellow, align: "center", alpha: scen === "ok" ? P("settle", 0.85, 1) : 0 });

    if (!fail) {
      // ---------------- Paso 3: balance check only (nothing signed)
      const chk = P("check", 0, 0.3), gone = 1 - P("settle", 0, 0.25);
      if (chk > 0 && gone > 0) {
        arrow(640, 290, 640, 404, chk, C.blue, 1.5);
        text("WalletBalance", 652, 360, { font: `12px ${MONO}`, color: C.blue, alpha: chk * gone });
        const ok = P("check", 0.3, 0.55);
        ctx.save(); ctx.globalAlpha = ok * gone; ctx.strokeStyle = C.green; ctx.lineWidth = 5; ctx.lineCap = "round"; ctx.lineJoin = "round";
        ctx.beginPath(); ctx.moveTo(620, 444); ctx.lineTo(636, 460); ctx.lineTo(664, 428); ctx.stroke(); ctx.restore();
        text("saldo suficiente", 640, 500, { font: `15px ${MONO}`, color: C.green, align: "center", alpha: ok * gone });
        text("no se firma nada todavía", 640, 528, { font: `italic 18px ${SERIF}`, color: C.dim, align: "center", alpha: P("check", 0.5, 0.75) * gone });
      }
      // ---------------- Paso 5: fund + sign, only with the invoice SETTLED
      const lease = P("fund", 0, 0.25);
      if (lease > 0) {
        ctx.save(); ctx.globalAlpha = lease; ctx.strokeStyle = C.blue; ctx.lineWidth = 2; ctx.setLineDash([5, 5]);
        ctx.beginPath(); ctx.arc(UTXOS[0].x, UTXO_Y, 26, 0, Math.PI * 2 * lease); ctx.stroke(); ctx.restore();
        text("FundPsbt · lease", UTXOS[0].x - 4, 380, { font: `12px ${MONO}`, color: C.blue, align: "center", alpha: lease * (1 - P("publish", 0.4, 0.6)) });
      }
      const card = P("fund", 0.2, 0.55);
      const shrink = P("publish", 0.15, 0.45);
      if (card > 0 && shrink < 1) {
        const x = 490, y = 398, w = 300, h = 140;
        ctx.save(); ctx.globalAlpha = card * (1 - shrink);
        rr(x, y, w, h, 10); ctx.fillStyle = "#15171a"; ctx.fill();
        const per = 2 * (w + h); ctx.strokeStyle = C.gold; ctx.lineWidth = 1.5; ctx.setLineDash([per * card, per]); ctx.stroke();
        ctx.restore();
        const a = card * (1 - shrink);
        text("tx 07c7…4966", x + 16, y + 28, { font: `600 14px ${MONO}`, color: C.gold, alpha: a });
        coin(x + 34, y + 72, C.gold, 12, a);
        text("UTXO", x + 34, y + 104, { font: `12px ${MONO}`, color: C.dim, align: "center", alpha: a });
        arrow(x + 58, y + 72, x + 112, y + 72, a > 0 ? 1 : 0, C.dim, 1.5);
        text("99.169 → bc1qmefue…", x + 122, y + 62, { font: `14px ${MONO}`, color: C.gold, alpha: a });
        text("cambio → nodo", x + 122, y + 84, { font: `13px ${MONO}`, color: C.dim, alpha: a });
        text("minería 131 (1 sat/vB)", x + 122, y + 104, { font: `13px ${MONO}`, color: C.dim, alpha: a });
        const signed = P("fund", 0.6, 0.75);
        stamp(after("publish", 0) ? "TRANSMITIDA" : "FIRMADA · GUARDADA · SIN TRANSMITIR", x + w / 2, y + 120,
          after("publish", 0) ? C.green : C.yellow, signed * (1 - shrink));
      }
      // ---------------- Paso 5: publish → block → cold
      const toBlock = P("publish", 0.35, 0.6), toCold = P("publish", 0.7, 0.95);
      const BL = { x: 1000, y: 430 };
      const blockIn = P("publish", 0.45, 0.6);
      if (blockIn > 0) {
        ctx.save(); ctx.globalAlpha = blockIn; ctx.strokeStyle = C.green; ctx.lineWidth = 2;
        rr(BL.x - 46, BL.y - 46, 92, 92, 6); ctx.stroke();
        ctx.strokeStyle = C.faint; for (let i = 1; i < 4; i++) { ctx.beginPath(); ctx.moveTo(BL.x - 34, BL.y - 46 + i * 23); ctx.lineTo(BL.x + 34, BL.y - 46 + i * 23); ctx.stroke(); }
        ctx.restore();
        text("bloque", BL.x, BL.y + 72, { font: `13px ${MONO}`, color: C.green, align: "center", alpha: blockIn });
      }
      if (toBlock > 0 && toCold < 1) {
        const x = toCold > 0 ? lerp(BL.x, COLD.x + COLD.w / 2, toCold) : lerp(640, BL.x, toBlock);
        const y = toCold > 0 ? lerp(BL.y, 300, toCold) : lerp(485, BL.y, toBlock) - Math.sin(toBlock * Math.PI) * 40;
        ctx.save(); rr(x - 20, y - 14, 40, 28, 5); ctx.fillStyle = C.gold; ctx.fill(); ctx.restore();
      }
      const arrived = P("publish", 0.9, 1);
      for (let i = 0; i < 4; i++) { const c = coldCoin(i); coin(c.x, c.y, C.gold, 11, arrived); }
      text("+99.169 sats", COLD.x + COLD.w / 2, 326, { font: `16px ${MONO}`, color: C.green, align: "center", alpha: arrived });
    } else {
      // ---------------- fail: balance check says no
      const tryF = P("fail", 0, 0.3);
      arrow(640, 290, 640, 412, tryF, C.blue, 1.5);
      text("WalletBalance", 652, 360, { font: `12px ${MONO}`, color: C.blue, alpha: tryF });
      const rej = P("fail", 0.3, 0.55);
      if (rej > 0) {
        ctx.save(); ctx.globalAlpha = rej; ctx.strokeStyle = C.red; ctx.lineWidth = 5; ctx.lineCap = "round";
        const cx = 640, cy = 450, r = 22 * rej;
        ctx.beginPath(); ctx.moveTo(cx - r, cy - r); ctx.lineTo(cx + r, cy + r); ctx.moveTo(cx + r, cy - r); ctx.lineTo(cx - r, cy + r); ctx.stroke(); ctx.restore();
        text("saldo insuficiente", 640, 505, { font: `15px ${MONO}`, color: C.red, align: "center", alpha: rej });
        text("nada cobrado · nada firmado", 640, 530, { font: `italic 18px ${SERIF}`, color: C.dim, align: "center", alpha: P("fail", 0.55, 0.8) });
      }
      const cancel = P("refund", 0, 0.3);
      arrow(NODE.x - 4, 300, PAYER.x + PAYER.w + 8, 300, cancel, C.red, 1.5);
      text("CancelInvoice", (PAYER.x + PAYER.w + NODE.x) / 2, 320, { font: `12px ${MONO}`, color: C.red, align: "center", alpha: cancel });
      text("vuelven 100.000 sats", PAYER.x + PAYER.w / 2, 370, { font: `italic 19px ${SERIF}`, color: C.green, align: "center", alpha: P("refund", 0.85, 1) });
    }

    // ---------------- state machine row
    drawChips(labels);

    // ---------------- caption
    if (cur.cap) {
      const s = scene(cur.k), local = clamp((t - s.a) / 0.5), out = 1 - clamp((t - (s.b - 0.35)) / 0.35);
      const lines = wrap(cur.cap, 1060, `22px ${SERIF}`);
      lines.forEach((ln, i) => text(ln, W / 2, 566 + i * 28, { font: `22px ${SERIF}`, color: C.ink, align: "center", alpha: Math.min(local, cur.k === "ledger" ? 1 : out) }));
    }

    // ---------------- ledger overlay
    if (after("ledger", 0)) drawLedger(P("ledger", 0, 0.25), fail);
  }

  function chipRow(chips, at, y, label, alpha, finalBad) {
    let idx = -1, since = -1;
    for (const [ts, i] of at) if (t >= ts) { idx = i; since = ts; }
    ctx.save(); ctx.globalAlpha = alpha; ctx.font = `600 13px ${MONO}`;
    const pad = 14, gap = 30;
    const widths = chips.map((c) => ctx.measureText(c).width + pad * 2);
    const totalW = widths.reduce((a2, b2) => a2 + b2, 0) + gap * (chips.length - 1);
    let x = W / 2 - totalW / 2 + 60;
    ctx.textAlign = "right"; ctx.fillStyle = C.dim; ctx.font = `12px ${MONO}`;
    ctx.fillText(label, x - 22, y + 4);
    ctx.font = `600 13px ${MONO}`;
    chips.forEach((c, i) => {
      const w = widths[i], active = i === idx, done = i < idx;
      const bad = c === "FAILED" || c === "CANCELED";
      const last = i === chips.length - 1;
      const col = active ? (bad ? C.red : c === "ACCEPTED" ? C.yellow : last ? C.green : C.blue) : done ? C.dim : C.faint;
      rr(x, y - 15, w, 30, 15);
      if (active) { ctx.fillStyle = col; ctx.fill(); ctx.fillStyle = C.bg; }
      else { ctx.strokeStyle = col; ctx.lineWidth = 1.5; ctx.stroke(); ctx.fillStyle = col; }
      ctx.textAlign = "center"; ctx.fillText(c, x + w / 2, y + 5);
      if (active && c === "ACCEPTED") {  // the moment the payment is held
        const q = clamp((t - since) / 1.2);
        if (q < 1) { ctx.save(); ctx.globalAlpha = alpha * (1 - q); ctx.strokeStyle = C.yellow; ctx.lineWidth = 2;
          rr(x - 8 * q, y - 15 - 8 * q, w + 16 * q, 30 + 16 * q, 15 + 8 * q); ctx.stroke(); ctx.restore(); }
      }
      if (!last) { ctx.fillStyle = C.faint; ctx.fillText("→", x + w + gap / 2, y + 5); }
      x += w + gap;
    });
    ctx.restore();
  }

  function drawChips(alpha) {
    const sc = SCEN[scen];
    chipRow(sc.inv, sc.invAt, 634, "invoice · LND", alpha);
    chipRow(sc.chips, sc.chipAt, 680, "swap · ln2oc", alpha);
  }

  function drawLedger(p, fail) {
    ctx.save(); ctx.globalAlpha = 0.9 * p; ctx.fillStyle = C.bg; ctx.fillRect(0, 96, W, 470); ctx.restore();
    // Four parties: the swap came through a community, which is owed 0.1 % of the 0.7 % fee.
    const cols = [480, 680, 870, 1060]; const rowY = [240, 294, 348, 414];
    const a = p;
    ["Pagador", "Operador", "Comunidad", "Vos (cold wallet)"].forEach((h, c) =>
      text(h, cols[c], 186, { font: `600 22px ${SERIF}`, align: "center", alpha: a }));
    text("Lightning", 260, rowY[0], { font: `15px ${MONO}`, color: C.yellow, alpha: a });
    text("on-chain", 260, rowY[1], { font: `15px ${MONO}`, color: C.gold, alpha: a });
    text("comisión 0,1 %", 260, rowY[2] - 8, { font: `15px ${MONO}`, color: C.blue, alpha: a });
    text("(se paga a mano)", 260, rowY[2] + 12, { font: `12px ${MONO}`, color: C.dim, alpha: a });
    text("neto", 260, rowY[3], { font: `15px ${MONO}`, color: C.dim, alpha: a });
    ctx.save(); ctx.globalAlpha = a; ctx.strokeStyle = C.faint; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(250, 380); ctx.lineTo(1160, 380); ctx.stroke(); ctx.restore();
    const v = fail
      ? [["0", "0", "—", "—"], ["—", "0", "—", "0"], ["—", "0", "0", "—"], ["0", "0", "0", "0"]]
      : [["−100.000", "+100.000", "—", "—"], ["—", "−99.300", "—", "+99.169"],
         ["—", "−100", "+100", "—"], ["−100.000", "+600", "+100", "+99.169"]];
    const colr = (s) => (s.startsWith("+") ? C.green : s.startsWith("−") ? C.red : C.dim);
    v.forEach((row, r) => row.forEach((s, c) => {
      const w = P("ledger", 0.15 + 0.08 * r, 0.35 + 0.08 * r);
      text(s, cols[c], rowY[r], { font: `${r === 3 ? "600 " : ""}26px ${SERIF}`, color: colr(s), align: "center", write: w, alpha: a });
    }));
    text(fail ? "Nadie perdió un sat." : "Los 131 restantes se los llevaron los mineros, a 1 sat/vB.", W / 2, 486,
      { font: `italic 22px ${SERIF}`, color: C.dim, align: "center", alpha: P("ledger", 0.5, 0.7) });
  }

  // ---------------------------------------------------------------- user view
  const PH = { x: 110, y: 118, w: 250, h: 410 };
  const MB = { x: 92, y: 168, w: 290, h: 300 };
  const BOX = { x: 540, y: 236, w: 220, h: 150 };
  const CW = { x: 950, y: 206, w: 250, h: 210 };
  const PURPLE = "#b189d6";
  function bolt(x, y, s, color, alpha = 1) {
    if (alpha <= 0) return;
    ctx.save(); ctx.globalAlpha *= Math.min(1, alpha); ctx.translate(x, y); ctx.scale(s, s);
    ctx.beginPath(); ctx.moveTo(5, -22); ctx.lineTo(-11, 3); ctx.lineTo(-1, 3); ctx.lineTo(-6, 22); ctx.lineTo(11, -5); ctx.lineTo(1, -5); ctx.closePath();
    ctx.fillStyle = color; ctx.fill(); ctx.restore();
  }
  function panel(b, r, stroke, alpha, fill = "#14161a", lw = 2) {
    if (alpha <= 0) return;
    ctx.save(); ctx.globalAlpha *= Math.min(1, alpha); rr(b.x, b.y, b.w, b.h, r);
    ctx.fillStyle = fill; ctx.fill(); ctx.strokeStyle = stroke; ctx.lineWidth = lw; ctx.stroke(); ctx.restore();
  }
  function fly(from, to, q, arcH) {
    return { x: lerp(from.x, to.x, q), y: lerp(from.y, to.y, q) - Math.sin(q * Math.PI) * arcH };
  }
  function packet(x, y, alpha = 1) {
    if (alpha <= 0) return;
    ctx.save(); ctx.globalAlpha *= Math.min(1, alpha); rr(x - 20, y - 14, 40, 28, 6); ctx.fillStyle = C.gold; ctx.fill(); ctx.restore();
  }

  function frameUser() {
    const cur = current();
    if (cur.step) {
      text(cur.step, 70, 74, { font: `600 15px ${MONO}`, color: C.dim });
      text(cur.title, 70 + (cur.step.length + 2) * 9.6, 74, { font: `italic 24px ${SERIF}`, color: C.ink });
    }
    text("Lo que ve el usuario", W - 70, 74, { font: `15px ${MONO}`, color: C.dim, align: "right" });

    const appear = P("u-addr", 0, 0.3), lab = P("u-addr", 0.12, 0.4), sideA = P("u-addr", 0.2, 0.5);

    // guide arrows: wallet -> ln2oc -> cold wallet
    ctx.save(); ctx.globalAlpha = sideA * 0.7; ctx.strokeStyle = C.faint; ctx.lineWidth = 2; ctx.setLineDash([6, 7]);
    ctx.beginPath(); ctx.moveTo(392, 311); ctx.lineTo(528, 311); ctx.moveTo(772, 311); ctx.lineTo(938, 311); ctx.stroke(); ctx.restore();
    text("Lightning", 460, 300, { font: `12px ${MONO}`, color: C.yellow, align: "center", alpha: sideA });
    text("on-chain", 855, 300, { font: `12px ${MONO}`, color: C.gold, align: "center", alpha: sideA });

    // ln2oc: an isolated service with its own dedicated node
    panel(BOX, 16, C.blue, sideA);
    text("ln2oc.com", BOX.x + BOX.w / 2, BOX.y + 58, { font: `600 30px ${SERIF}`, align: "center", alpha: sideA });
    text("servicio aislado", BOX.x + BOX.w / 2, BOX.y + 94, { font: `13px ${MONO}`, color: C.dim, align: "center", alpha: sideA });
    text("nodo LN dedicado", BOX.x + BOX.w / 2, BOX.y + 114, { font: `13px ${MONO}`, color: C.dim, align: "center", alpha: sideA });

    // cold wallet with incoming txs
    panel(CW, 16, C.ink, sideA);
    text("Tu cold wallet", CW.x + CW.w / 2, CW.y + 46, { font: `600 26px ${SERIF}`, align: "center", alpha: sideA });
    text("tus llaves, offline", CW.x + CW.w / 2, CW.y + 72, { font: `italic 18px ${SERIF}`, color: C.dim, align: "center", alpha: sideA });
    const in1 = P("u-pay", 0.85, 1), in2 = P("u-p2p", 0.9, 1);
    text("+99.169 sats", CW.x + 24, CW.y + 122, { font: `600 22px ${SERIF}`, color: C.green, alpha: in1 });
    text("desde tu wallet LN", CW.x + 24, CW.y + 142, { font: `12px ${MONO}`, color: C.dim, alpha: in1 });
    text("+99.169 sats", CW.x + 24, CW.y + 178, { font: `600 22px ${SERIF}`, color: C.green, alpha: in2 });
    text("trade P2P", CW.x + 24, CW.y + 198, { font: `12px ${MONO}`, color: C.dim, alpha: in2 });

    // the phone (hidden while the P2P trade card is shown)
    let phA = 1;
    if (after("u-p2p")) phA = 1 - P("u-p2p", 0, 0.12);
    if (after("u-fail")) phA = P("u-fail", 0.06, 0.2);
    if (phA > 0) {
      ctx.save(); ctx.globalAlpha = phA;
      rr(PH.x, PH.y, PH.w, PH.h, 30); ctx.fillStyle = "#14161a"; ctx.globalAlpha = phA * appear; ctx.fill(); ctx.globalAlpha = phA;
      rr(PH.x, PH.y, PH.w, PH.h, 30); const per = 2 * (PH.w + PH.h);
      ctx.strokeStyle = C.ink; ctx.lineWidth = 2; ctx.setLineDash([per * appear, per]); ctx.stroke(); ctx.setLineDash([]);
      rr(PH.x + PH.w / 2 - 34, PH.y + 12, 68, 8, 4); ctx.fillStyle = C.faint; ctx.globalAlpha = phA * lab; ctx.fill();
      ctx.restore();
      const A = lab * phA, X = PH.x + 22;
      const failing = after("u-fail");
      text("tu wallet Lightning", PH.x + PH.w / 2, PH.y + 50, { font: `italic 19px ${SERIF}`, color: C.ink, align: "center", alpha: A });
      text("Wallet of Satoshi · Phoenix · …", PH.x + PH.w / 2, PH.y + 70, { font: `11px ${MONO}`, color: C.dim, align: "center", alpha: A });
      text("Saldo", X, PH.y + 106, { font: `12px ${MONO}`, color: C.dim, alpha: A });
      const bal = after("u-pay", 0.6) ? "100.000 sats" : "200.000 sats";
      const untouched = failing && after("u-fail", 0.85);
      text(bal, X, PH.y + 134, { font: `600 24px ${SERIF}`, color: untouched ? C.green : C.ink, alpha: A });
      text("intacto", PH.x + PH.w - 22, PH.y + 134, { font: `600 12px ${MONO}`, color: C.green, align: "right", alpha: A * (untouched ? 1 : 0) });
      text("Enviar a", X, PH.y + 172, { font: `12px ${MONO}`, color: C.dim, alpha: A });
      ctx.save(); ctx.globalAlpha = A; rr(PH.x + 16, PH.y + 182, PH.w - 32, 92, 10); ctx.strokeStyle = C.faint; ctx.lineWidth = 1.5; ctx.stroke(); ctx.restore();
      const w1 = failing ? 1 : P("u-addr", 0.3, 0.5), w2 = failing ? 1 : P("u-addr", 0.45, 0.65), w3 = failing ? 1 : P("u-addr", 0.7, 0.88);
      text("bc1qmefue372ssa4zffa4n0", X + 6, PH.y + 210, { font: `14px ${MONO}`, color: C.gold, write: w1, alpha: A });
      text("hqadscqp2myg9utwrtr", X + 6, PH.y + 230, { font: `14px ${MONO}`, color: C.gold, write: w2, alpha: A });
      text("@ln2oc.com", X + 6, PH.y + 260, { font: `600 16px ${MONO}`, color: C.blue, write: w3, alpha: A });
      if (!failing) pulse(X + 60, PH.y + 255, P("u-addr", 0.85, 1), C.blue);
      text("Monto", X, PH.y + 306, { font: `12px ${MONO}`, color: C.dim, alpha: A });
      text("100.000 sats", X, PH.y + 334, { font: `600 24px ${SERIF}`, alpha: A });

      // pay button state
      let label = "Pagar", style = "fill", col = C.yellow;
      if (!failing) {
        if (after("u-pay", 0.12)) { label = "Pagando…"; style = "line"; }
        if (after("u-pay", 0.6)) { label = "Pagado ✓"; style = "fill"; col = C.green; }
      } else {
        if (after("u-fail", 0.25)) { label = "Pagando…"; style = "line"; }
        if (after("u-fail", 0.85)) { label = "Pago fallido"; style = "line"; col = C.red; }
      }
      const btn = { x: PH.x + 16, y: PH.y + 352, w: PH.w - 32, h: 42 };
      ctx.save(); ctx.globalAlpha = A; rr(btn.x, btn.y, btn.w, btn.h, 21);
      if (style === "fill") { ctx.fillStyle = col; ctx.fill(); } else { ctx.strokeStyle = col; ctx.lineWidth = 2; ctx.stroke(); }
      ctx.restore();
      text(label, btn.x + btn.w / 2, btn.y + 28, { font: `600 16px ${MONO}`, color: style === "fill" ? C.bg : col, align: "center", alpha: A });
      pulse(btn.x + btn.w / 2, btn.y + 21, failing ? P("u-fail", 0.2, 0.32) : P("u-pay", 0.05, 0.2), C.yellow);
    }

    // the P2P trade card
    const mA = after("u-fail") ? 1 - P("u-fail", 0, 0.1) : P("u-p2p", 0.08, 0.25);
    if (mA > 0) {
      panel(MB, 16, PURPLE, mA);
      const X = MB.x + 24;
      text("Exchange P2P", MB.x + MB.w / 2, MB.y + 48, { font: `600 30px ${SERIF}`, align: "center", alpha: mA });
      text("por ejemplo, Mostro", MB.x + MB.w / 2, MB.y + 74, { font: `italic 17px ${SERIF}`, color: C.dim, align: "center", alpha: mA });
      text("Compraste 100.000 sats", X, MB.y + 122, { font: `20px ${SERIF}`, write: P("u-p2p", 0.2, 0.32), alpha: mA });
      text("recibir en", X, MB.y + 160, { font: `12px ${MONO}`, color: C.dim, alpha: mA * P("u-p2p", 0.28, 0.36) });
      ctx.font = `14px ${MONO}`; const gw = ctx.measureText("bc1qmefue372…").width;
      text("bc1qmefue372…", X, MB.y + 186, { font: `14px ${MONO}`, color: C.gold, alpha: mA * P("u-p2p", 0.3, 0.4) });
      text("@ln2oc.com", X + gw, MB.y + 186, { font: `600 14px ${MONO}`, color: C.blue, alpha: mA * P("u-p2p", 0.34, 0.44) });
      text("el vendedor liberó ✓", X, MB.y + 236, { font: `600 14px ${MONO}`, color: C.green, alpha: mA * P("u-p2p", 0.44, 0.52) });
      text("te paga a tu Lightning Address", X, MB.y + 262, { font: `12px ${MONO}`, color: C.dim, alpha: mA * P("u-p2p", 0.48, 0.56) });
    }

    // flights
    const boxIn = { x: BOX.x - 14, y: BOX.y + 75 }, boxOut = { x: BOX.x + BOX.w + 18, y: BOX.y + 75 };
    const btnOut = { x: PH.x + PH.w + 16, y: PH.y + 373 };
    let q = P("u-pay", 0.12, 0.4);
    if (q > 0 && q < 1) { const f = fly(btnOut, boxIn, q, 60); bolt(f.x, f.y, 1, C.yellow); }
    pulse(BOX.x + BOX.w / 2, BOX.y + BOX.h / 2, P("u-pay", 0.4, 0.6), C.blue);
    q = P("u-pay", 0.55, 0.85);
    if (q > 0 && q < 1) { const f = fly(boxOut, { x: CW.x - 12, y: CW.y + 118 }, q, 40); packet(f.x, f.y); }

    q = P("u-p2p", 0.5, 0.7);
    if (q > 0 && q < 1) { const f = fly({ x: MB.x + MB.w + 14, y: MB.y + 150 }, boxIn, q, 50); bolt(f.x, f.y, 1, C.yellow); }
    pulse(BOX.x + BOX.w / 2, BOX.y + BOX.h / 2, P("u-p2p", 0.7, 0.85), C.blue);
    q = P("u-p2p", 0.72, 0.9);
    if (q > 0 && q < 1) { const f = fly(boxOut, { x: CW.x - 12, y: CW.y + 174 }, q, 40); packet(f.x, f.y); }

    q = P("u-fail", 0.25, 0.5);
    if (q > 0 && q < 1) { const f = fly(btnOut, boxIn, q, 60); bolt(f.x, f.y, 1, C.yellow); }
    const nofunds = P("u-fail", 0.5, 0.6);
    if (nofunds > 0) {
      pulse(BOX.x + BOX.w / 2, BOX.y + BOX.h / 2, P("u-fail", 0.5, 0.65), C.red);
      text("sin fondos on-chain", BOX.x + BOX.w / 2, BOX.y + BOX.h + 30, { font: `14px ${MONO}`, color: C.red, align: "center", alpha: nofunds });
      text("el pago se rechaza", BOX.x + BOX.w / 2, BOX.y + BOX.h + 52, { font: `italic 18px ${SERIF}`, color: C.dim, align: "center", alpha: P("u-fail", 0.58, 0.68) });
    }
    q = P("u-fail", 0.62, 0.85);
    if (q > 0 && q < 1) { const f = fly(boxIn, btnOut, q, 60); bolt(f.x, f.y, 1, C.red); }

    // caption
    if (cur.cap) {
      const sc = scene(cur.k), local = clamp((t - sc.a) / 0.5), out = 1 - clamp((t - (sc.b - 0.35)) / 0.35);
      wrap(cur.cap, 1060, `22px ${SERIF}`).forEach((ln, i) =>
        text(ln, W / 2, 602 + i * 30, { font: `22px ${SERIF}`, align: "center", alpha: Math.min(local, out) }));
    }

    // closing card
    if (after("u-end")) {
      const p = P("u-end", 0, 0.2);
      ctx.save(); ctx.globalAlpha = 0.92 * p; ctx.fillStyle = C.bg; ctx.fillRect(0, 96, W, H - 96); ctx.restore();
      text("Una dirección. Un pago. Sats en frío.", W / 2, 320, { font: `600 46px ${SERIF}`, align: "center", write: P("u-end", 0.1, 0.5), alpha: p });
      ctx.font = `600 22px ${MONO}`;
      const a1 = "bc1qmefue372…", a2 = "@ln2oc.com", w1 = ctx.measureText(a1).width, w2 = ctx.measureText(a2).width;
      const x0 = W / 2 - (w1 + w2) / 2, la = P("u-end", 0.4, 0.6);
      text(a1, x0, 390, { font: `600 22px ${MONO}`, color: C.gold, alpha: la });
      text(a2, x0 + w1, 390, { font: `600 22px ${MONO}`, color: C.blue, alpha: la });
      text("ln2oc corre aislado: su propio nodo Lightning y su propio dominio.", W / 2, 460,
        { font: `italic 24px ${SERIF}`, color: C.dim, align: "center", alpha: P("u-end", 0.55, 0.8) });
    }
  }


  function frameCommunity() {
    const cur = current();
    if (cur.step) {
      text(cur.step, 70, 74, { font: `600 15px ${MONO}`, color: C.dim });
      text(cur.title, 70 + (cur.step.length + 2) * 9.6, 74, { font: `italic 24px ${SERIF}`, color: C.ink });
    }
    text("Comunidades", W - 70, 74, { font: `15px ${MONO}`, color: C.dim, align: "right" });

    const show = P("c-hook", 0, 0.25), lab = P("c-hook", 0.1, 0.35);
    // the community's app
    panel(MB, 16, PURPLE, show);
    const X = MB.x + 24;
    text("Tu comunidad", MB.x + MB.w / 2, MB.y + 46, { font: `600 28px ${SERIF}`, align: "center", alpha: lab });
    text("exchange P2P · wallet · pagos", MB.x + MB.w / 2, MB.y + 72, { font: `12px ${MONO}`, color: C.dim, align: "center", alpha: lab });
    text("Retirar on-chain", X, MB.y + 116, { font: `600 18px ${SERIF}`, alpha: lab });
    text("pide la invoice a", X, MB.y + 148, { font: `12px ${MONO}`, color: C.dim, alpha: lab });
    text("/.well-known/lnurlp/", X, MB.y + 172, { font: `13px ${MONO}`, color: C.dim, write: P("c-hook", 0.25, 0.4), alpha: lab });
    text("bc1qmefue372…", X, MB.y + 192, { font: `13px ${MONO}`, color: C.gold, write: P("c-hook", 0.35, 0.5), alpha: lab });
    text("?community=", X, MB.y + 220, { font: `600 15px ${MONO}`, color: PURPLE, write: P("c-hook", 0.5, 0.62), alpha: lab });
    text("tu-comunidad", X, MB.y + 242, { font: `600 15px ${MONO}`, color: PURPLE, write: P("c-hook", 0.6, 0.74), alpha: lab });
    pulse(X + 80, MB.y + 230, P("c-hook", 0.74, 0.92), PURPLE);
    // owed counter (inside the community panel)
    const sum = after("c-sum"), paid = after("c-paid", 0.55);
    let owed = after("c-split", 0.7) ? 100 : 0;
    if (sum) for (let i = 0; i < 3; i++) if (P("c-sum", 0.15 + i * 0.22, 0.35 + i * 0.22) >= 1) owed += 100;
    if (paid) owed = 0;
    const oA = P("c-split", 0.6, 0.8);
    text("se te debe", X, MB.y + 266, { font: `12px ${MONO}`, color: C.dim, alpha: oA });
    text(`${owed.toLocaleString("es-AR")} sats`, MB.x + MB.w - 24, MB.y + 266, { font: `600 18px ${SERIF}`, color: paid ? C.green : PURPLE, align: "right", alpha: oA });

    // ln2oc and the cold wallet
    const sideA = P("c-hook", 0.15, 0.4);
    ctx.save(); ctx.globalAlpha = sideA * 0.7; ctx.strokeStyle = C.faint; ctx.lineWidth = 2; ctx.setLineDash([6, 7]);
    ctx.beginPath(); ctx.moveTo(398, 311); ctx.lineTo(528, 311); ctx.moveTo(772, 311); ctx.lineTo(938, 311); ctx.stroke(); ctx.restore();
    text("Lightning", 462, 300, { font: `12px ${MONO}`, color: C.yellow, align: "center", alpha: sideA });
    text("on-chain", 855, 300, { font: `12px ${MONO}`, color: C.gold, align: "center", alpha: sideA });
    panel(BOX, 16, C.blue, sideA);
    text("ln2oc", BOX.x + BOX.w / 2, BOX.y + 58, { font: `600 30px ${SERIF}`, align: "center", alpha: sideA });
    text("el operador", BOX.x + BOX.w / 2, BOX.y + 94, { font: `13px ${MONO}`, color: C.dim, align: "center", alpha: sideA });
    text("nodo LN dedicado", BOX.x + BOX.w / 2, BOX.y + 114, { font: `13px ${MONO}`, color: C.dim, align: "center", alpha: sideA });
    panel(CW, 16, C.ink, sideA);
    text("Cold wallet", CW.x + CW.w / 2, CW.y + 46, { font: `600 26px ${SERIF}`, align: "center", alpha: sideA });
    text("de tu usuario", CW.x + CW.w / 2, CW.y + 72, { font: `italic 18px ${SERIF}`, color: C.dim, align: "center", alpha: sideA });
    const in1 = P("c-pay", 0.75, 0.95);
    text("+99.169 sats", CW.x + 24, CW.y + 130, { font: `600 22px ${SERIF}`, color: C.green, alpha: in1 });
    text("100.000 − 700 − minería", CW.x + 24, CW.y + 152, { font: `12px ${MONO}`, color: C.dim, alpha: in1 });

    // flights: the user's payment
    const boxIn = { x: BOX.x - 14, y: BOX.y + 75 }, boxOut = { x: BOX.x + BOX.w + 18, y: BOX.y + 75 };
    const mbOut = { x: MB.x + MB.w + 14, y: MB.y + 150 };
    let q = P("c-pay", 0.1, 0.4);
    if (q > 0 && q < 1) { const f = fly(mbOut, boxIn, q, 50); bolt(f.x, f.y, 1, C.yellow); }
    pulse(BOX.x + BOX.w / 2, BOX.y + BOX.h / 2, P("c-pay", 0.4, 0.6), C.blue);
    q = P("c-pay", 0.5, 0.8);
    if (q > 0 && q < 1) { const f = fly(boxOut, { x: CW.x - 12, y: CW.y + 126 }, q, 40); packet(f.x, f.y); }

    // the fee split, under ln2oc
    const sA = P("c-split", 0, 0.2);
    if (sA > 0) {
      const bx = 470, by = 430, bw = 360, bh = 26;
      text("comisión: 700 sats (0,7 %)", bx + bw / 2, by - 12, { font: `13px ${MONO}`, color: C.dim, align: "center", alpha: sA });
      const sp = P("c-split", 0.25, 0.55), cw = (bw * 100) / 700;
      ctx.save(); ctx.globalAlpha = sA;
      rr(bx, by, bw, bh, 6); ctx.fillStyle = C.blue; ctx.globalAlpha = sA * 0.85; ctx.fill();
      ctx.globalAlpha = sA * sp; rr(bx + bw - cw, by, cw, bh, 6); ctx.fillStyle = PURPLE; ctx.fill();
      ctx.restore();
      text("600 · operador", bx + 10, by + bh + 22, { font: `600 13px ${MONO}`, color: C.blue, alpha: sA * sp });
      text("100 · comunidad", bx + bw, by + bh + 22, { font: `600 13px ${MONO}`, color: PURPLE, align: "right", alpha: sA * sp });
      const fq = P("c-split", 0.6, 0.85);
      if (fq > 0 && fq < 1) { const f = fly({ x: bx + bw - cw / 2, y: by }, { x: MB.x + MB.w - 60, y: MB.y + 258 }, fq, 80); coin(f.x, f.y, PURPLE, 9); }
    }
    // more withdrawals accrue
    if (sum && !after("c-paid")) {
      for (let i = 0; i < 3; i++) {
        const qq = P("c-sum", 0.15 + i * 0.22, 0.35 + i * 0.22);
        if (qq > 0 && qq < 1) {
          const f = fly(mbOut, boxIn, qq, 40); bolt(f.x, f.y, 0.7, C.yellow);
          const g = fly(boxOut, { x: CW.x - 12, y: CW.y + 126 }, qq, 30); packet(g.x, g.y, 0.8);
        }
      }
    }
    // the operator pays the community over Lightning
    q = P("c-paid", 0.15, 0.55);
    if (q > 0 && q < 1) { const f = fly(boxIn, { x: MB.x + MB.w + 14, y: MB.y + 270 }, q, -40); bolt(f.x, f.y, 1, PURPLE); }
    text("pagado por Lightning ✓", X, MB.y + 288, { font: `600 12px ${MONO}`, color: C.green, alpha: P("c-paid", 0.55, 0.7) * (after("c-end") ? 0 : 1) });

    if (cur.cap) {
      const sc = scene(cur.k), local = clamp((t - sc.a) / 0.5), out = 1 - clamp((t - (sc.b - 0.35)) / 0.35);
      wrap(cur.cap, 1060, `22px ${SERIF}`).forEach((ln, i) =>
        text(ln, W / 2, 602 + i * 30, { font: `22px ${SERIF}`, align: "center", alpha: Math.min(local, out) }));
    }
    if (after("c-end")) {
      const p = P("c-end", 0, 0.2);
      ctx.save(); ctx.globalAlpha = 0.92 * p; ctx.fillStyle = C.bg; ctx.fillRect(0, 96, W, H - 96); ctx.restore();
      text("Tus usuarios retiran on-chain.", W / 2, 300, { font: `600 46px ${SERIF}`, align: "center", write: P("c-end", 0.1, 0.45), alpha: p });
      text("Vos te llevás una parte.", W / 2, 362, { font: `600 46px ${SERIF}`, color: PURPLE, align: "center", write: P("c-end", 0.35, 0.65), alpha: p });
      text("Sin construir nada: un parámetro en la URL.", W / 2, 440,
        { font: `italic 24px ${SERIF}`, color: C.dim, align: "center", alpha: P("c-end", 0.6, 0.85) });
    }
  }

  // ---------------------------------------------------------------- UI
  // Everything is looked up inside root (data-flow attributes, no ids): several players
  // can live on one page. Off-screen players pause; one the viewer paused stays paused.
  const q$ = (n) => root.querySelector(`[data-flow=${n}]`);
  const playBtn = q$("play"), scrub = q$("scrub"), timeEl = q$("time"), chaptersEl = q$("chapters");
  const scenBtns = [...root.querySelectorAll("[data-scen]")];
  let userPaused = false, visible = false;
  function buildChapters() {
    if (!chaptersEl) return;
    chaptersEl.innerHTML = "";
    SCEN[scen].scenes.filter((s) => s.k !== "title").forEach((s) => {
      const b = document.createElement("button"); b.type = "button"; b.dataset.k = s.k;
      const sp = document.createElement("span"); sp.textContent = s.step || "Fin";
      b.append(sp, document.createTextNode(s.title));
      b.addEventListener("click", () => { t = s.a + 0.01; draw(); });
      chaptersEl.appendChild(b);
    });
  }
  function setPlaying(v) {
    playing = v; playBtn.textContent = v ? "❚❚ Pausa" : "▶ Reproducir"; playBtn.setAttribute("aria-label", v ? "Pausar" : "Reproducir");
    last = null;
    if (raf !== null) { cancelAnimationFrame(raf); raf = null; }
    if (v) raf = requestAnimationFrame(loop);
  }
  function draw() {
    frame();
    scrub.max = total(); scrub.value = t.toFixed(2);
    timeEl.textContent = `${t.toFixed(1).replace(".", ",")} / ${total()} s`;
    const k = current().k;
    chaptersEl?.querySelectorAll("button").forEach((b) => b.classList.toggle("now", b.dataset.k === k));
  }
  function loop(ts) {
    raf = null;
    if (!playing) return;
    if (last !== null) t += Math.min(0.1, (ts - last) / 1000);
    last = ts;
    if (t >= total()) { t = total(); draw(); setPlaying(false); return; }
    draw(); raf = requestAnimationFrame(loop);
  }
  function toggle() {
    if (!playing && t >= total()) t = 0;
    userPaused = playing;
    setPlaying(!playing);
  }
  playBtn.addEventListener("click", toggle);
  cv.addEventListener("click", toggle);
  q$("restart").addEventListener("click", () => { t = 0; userPaused = false; setPlaying(true); });
  scrub.addEventListener("input", () => { t = parseFloat(scrub.value); userPaused = true; if (playing) setPlaying(false); draw(); });
  function setScen(s) {
    scen = s; t = 0; userPaused = false;
    for (const b of scenBtns) b.setAttribute("aria-pressed", String(b.dataset.scen === s));
    buildChapters(); setPlaying(!reduced && visible); draw();
  }
  for (const b of scenBtns) b.addEventListener("click", () => setScen(b.dataset.scen));
  function resize() {
    const r = cv.getBoundingClientRect(), dpr = Math.min(window.devicePixelRatio || 1, 2);
    cv.width = Math.round(r.width * dpr); cv.height = Math.round(r.width * dpr * 9 / 16); draw();
  }
  window.addEventListener("resize", resize);
  const io = new IntersectionObserver(([e]) => {
    visible = e.isIntersecting;
    if (disposed || reduced) return;
    if (visible && !userPaused && !playing && t < total()) setPlaying(true);
    if (!visible && playing) setPlaying(false);
  }, { threshold: 0.35 });

  scen = SCEN[initial] ? initial : "user";
  for (const b of scenBtns) b.setAttribute("aria-pressed", String(b.dataset.scen === scen));
  buildChapters();
  if (reduced) { const sc = SCEN[scen].scenes; t = sc[Math.min(1, sc.length - 1)].b - 0.01; playing = false; }
  const fontsReady = document.fonts ? document.fonts.ready : Promise.resolve();
  Promise.race([fontsReady, new Promise((r) => setTimeout(r, 1500))]).then(() => {
    if (disposed) return;
    resize();
    io.observe(cv);
  });
  setPlaying(false);
  resize();

  return () => {
    disposed = true;
    io.disconnect();
    if (raf !== null) cancelAnimationFrame(raf);
    window.removeEventListener("resize", resize);
  };
}
