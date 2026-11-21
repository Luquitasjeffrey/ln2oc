/* Bitcoin address validation, mirroring the service (app/validator.py):
   bech32 v0 (20/32 bytes) and bech32m v1 (32 bytes) are accepted; Base58Check P2PKH/P2SH
   is recognized only to explain why it is not.
   Network-aware; runs entirely in the browser. */

export type Network = "mainnet" | "testnet" | "testnet4" | "regtest";

const CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l";
const B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";
const HRP: Record<Network, string> = { mainnet: "bc", testnet: "tb", testnet4: "tb", regtest: "bcrt" };
const B58_VERSIONS: Record<Network, { p2pkh: number; p2sh: number }> = {
  mainnet: { p2pkh: 0x00, p2sh: 0x05 },
  testnet: { p2pkh: 0x6f, p2sh: 0xc4 },
  testnet4: { p2pkh: 0x6f, p2sh: 0xc4 },
  regtest: { p2pkh: 0x6f, p2sh: 0xc4 },
};

export type AddressResult =
  | { state: "empty" }
  | { state: "ok"; addr: string; type: string }
  | { state: "error"; addr: string; msg: string };

function polymod(values: number[]): number {
  const G = [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3];
  let chk = 1;
  for (const v of values) {
    const top = chk >>> 25;
    chk = (((chk & 0x1ffffff) << 5) ^ v) >>> 0;
    for (let i = 0; i < 5; i++) if ((top >>> i) & 1) chk = (chk ^ G[i]) >>> 0;
  }
  return chk;
}

const hrpExpand = (h: string) =>
  [...h].map((c) => c.charCodeAt(0) >> 5).concat([0], [...h].map((c) => c.charCodeAt(0) & 31));

function convertbits(data: number[], from: number, to: number): number[] | null {
  let acc = 0;
  let bits = 0;
  const out: number[] = [];
  const maxv = (1 << to) - 1;
  for (const v of data) {
    if (v < 0 || v >> from) return null;
    acc = (acc << from) | v;
    bits += from;
    while (bits >= to) {
      bits -= to;
      out.push((acc >> bits) & maxv);
    }
    acc &= (1 << bits) - 1;
  }
  if (bits >= from || ((acc << (to - bits)) & maxv)) return null;
  return out;
}

type Partial = { type: string } | { wrongNet: true } | null;

function bech32(addr: string, network: Network): Partial {
  if (addr.toLowerCase() !== addr && addr.toUpperCase() !== addr) return null;
  const a = addr.toLowerCase();
  const pos = a.lastIndexOf("1");
  if (pos < 1 || pos + 7 > a.length || a.length > 90) return null;
  const hrp = a.slice(0, pos);
  if (hrp !== HRP[network]) return Object.values(HRP).includes(hrp) ? { wrongNet: true } : null;
  const data: number[] = [];
  for (const c of a.slice(pos + 1)) {
    const d = CHARSET.indexOf(c);
    if (d < 0) return null;
    data.push(d);
  }
  const check = polymod(hrpExpand(hrp).concat(data));
  const enc = check === 1 ? "bech32" : check === 0x2bc830a3 ? "bech32m" : null;
  if (!enc) return null;
  const ver = data[0];
  const prog = convertbits(data.slice(1, -6), 5, 8);
  if (!prog) return null;
  if (ver === 0 && enc === "bech32" && (prog.length === 20 || prog.length === 32))
    return { type: prog.length === 20 ? "SegWit (P2WPKH)" : "SegWit (P2WSH)" };
  if (ver === 1 && enc === "bech32m" && prog.length === 32) return { type: "Taproot (P2TR)" };
  return null;
}

async function sha256(data: Uint8Array): Promise<Uint8Array> {
  return new Uint8Array(await crypto.subtle.digest("SHA-256", data));
}

async function base58(addr: string, network: Network): Promise<Partial | { unverified: true }> {
  if (![...addr].every((c) => B58.includes(c))) return null;
  let n = 0n;
  for (const c of addr) n = n * 58n + BigInt(B58.indexOf(c));
  const bytes: number[] = [];
  while (n > 0n) {
    bytes.unshift(Number(n % 256n));
    n /= 256n;
  }
  for (const c of addr) {
    if (c === "1") bytes.unshift(0);
    else break;
  }
  if (bytes.length !== 25) return null;
  if (!(globalThis.crypto && crypto.subtle)) return { unverified: true };
  const h2 = await sha256(await sha256(new Uint8Array(bytes.slice(0, 21))));
  for (let i = 0; i < 4; i++) if (h2[i] !== bytes[21 + i]) return null;
  const v = B58_VERSIONS[network];
  if (bytes[0] === v.p2pkh) return { type: "Legacy (P2PKH)" };
  if (bytes[0] === v.p2sh) return { type: "Legacy (P2SH)" };
  if ([0x00, 0x05, 0x6f, 0xc4].includes(bytes[0])) return { wrongNet: true };
  return null;
}

/** Accept what people actually paste: "bitcoin:bc1...?amount=..", spaces, an old "...@domain". */
export function clean(raw: string): string {
  let s = raw.trim().replace(/\s+/g, "");
  s = s.replace(/^bitcoin:/i, "").split("?")[0];
  if (s.includes("@")) s = s.split("@")[0];
  return s;
}

const NET_NAME: Record<Network, string> = { mainnet: "mainnet", testnet: "testnet", testnet4: "testnet4", regtest: "regtest" };

export async function validateAddress(raw: string, network: Network): Promise<AddressResult> {
  const addr = clean(raw);
  if (!addr) return { state: "empty" };
  const b = bech32(addr, network);
  // A Lightning Address name may only be lowercase (LUD-16). bech32 is case-insensitive
  // (QR codes often carry it in uppercase), so it is lowercased. Base58 is not: a wallet
  // that lowercases it breaks it, so the service only accepts bech32 (app/validator.py).
  if (b && "type" in b) return { state: "ok", addr: addr.toLowerCase(), type: b.type };
  const r = b ?? (await base58(addr, network));
  if (r && "type" in r)
    return {
      state: "error",
      addr,
      msg: `Es una dirección legacy ${r.type.replace("Legacy ", "")}. No sirve para una Lightning Address: distingue mayúsculas y las wallets la pasan a minúsculas. Sacá una ${HRP[network]}1q… o ${HRP[network]}1p… de tu cold wallet.`,
    };
  if (r && "unverified" in r)
    return { state: "error", addr, msg: "Este navegador no puede verificar el checksum. Revisá la dirección a mano." };
  if (r && "wrongNet" in r)
    return { state: "error", addr, msg: `Es una dirección de otra red. Este servicio paga en ${NET_NAME[network]}.` };
  return { state: "error", addr, msg: "No es una dirección de Bitcoin válida. Copiala de nuevo desde tu cold wallet." };
}
