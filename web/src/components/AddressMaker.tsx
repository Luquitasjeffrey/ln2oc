import { useEffect, useRef, useState } from "react";
import { validateAddress, type AddressResult } from "../lib/address";
import { useInstanceInfo } from "../lib/info";
import { LnurlPay } from "./LnurlPay";

const EXAMPLE: Record<string, string> = {
  mainnet: "bc1qmefue372ssa4zffa4n0hqadscqp2myg9utwrtr",
  testnet: "tb1qw508d6qejxtdg4y5r3zarvary0c5xw7kxpjzsx",
  testnet4: "tb1qw508d6qejxtdg4y5r3zarvary0c5xw7kxpjzsx",
  regtest: "bcrt1qac9zasaevp62vwnnuylkm3vsy99gxahlm5n0tz",
};

/** "Armá tu Lightning Address": paste an address, get <address>@<domain>. Validated locally. */
export function AddressMaker({ withPay = false }: { withPay?: boolean }) {
  const { info } = useInstanceInfo();
  const [raw, setRaw] = useState("");
  const [result, setResult] = useState<AddressResult>({ state: "empty" });
  const [copyLabel, setCopyLabel] = useState("Copiar");
  const outRef = useRef<HTMLOutputElement>(null);
  const seq = useRef(0);

  useEffect(() => {
    const my = ++seq.current;
    validateAddress(raw, info.network).then((r) => {
      if (my === seq.current) setResult(r);
    });
  }, [raw, info.network]);

  const current = result.state === "ok" ? `${result.addr}@${info.domain}` : null;
  const shown = result.state === "empty" ? EXAMPLE[info.network] : result.addr;
  const status =
    result.state === "empty"
      ? "Ejemplo. Pegá una dirección de tu cold wallet y se arma sola."
      : result.state === "ok"
        ? `${result.type} · ${info.network} · checksum verificado`
        : result.msg;

  async function copy() {
    if (!current) return;
    let ok = false;
    try {
      await navigator.clipboard.writeText(current);
      ok = true;
    } catch {
      const out = outRef.current;
      if (out) {
        const range = document.createRange();
        range.selectNodeContents(out);
        const sel = getSelection();
        sel?.removeAllRanges();
        sel?.addRange(range);
      }
    }
    setCopyLabel(ok ? "Copiada" : "Seleccionada: copiala");
    setTimeout(() => setCopyLabel("Copiar"), 1800);
  }

  return (
    <div className="maker" data-state={result.state}>
      <label className="k" htmlFor="addr-in">
        Armá tu Lightning Address
      </label>
      <input
        id="addr-in"
        type="text"
        autoComplete="off"
        autoCapitalize="off"
        spellCheck={false}
        placeholder={`Pegá una dirección ${EXAMPLE[info.network].slice(0, info.network === "regtest" ? 5 : 3)}… de tu cold wallet`}
        value={raw}
        onChange={(e) => setRaw(e.target.value)}
      />
      <div className="maker-out">
        <output ref={outRef} className={`addr-out${result.state === "empty" ? " is-example" : ""}`} aria-live="polite">
          <span className="on">{shown}</span>
          <span className="at">@{info.domain}</span>
        </output>
        <button type="button" disabled={!current} onClick={copy}>
          {copyLabel}
        </button>
      </div>
      <p className="maker-status">{status}</p>
      {withPay && result.state === "ok" && <LnurlPay key={result.addr} addr={result.addr} />}
    </div>
  );
}
