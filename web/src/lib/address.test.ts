import { describe, expect, it } from "vitest";
import { clean, validateAddress } from "./address";

const ok = async (a: string, net: "mainnet" | "testnet" | "regtest" = "mainnet") => {
  const r = await validateAddress(a, net);
  return r.state === "ok" ? r.type : r.state === "error" ? `error: ${r.msg}` : "empty";
};

describe("validateAddress (same vectors as tests/test_swap_e2e.py::test_address_to_script)", () => {
  it("accepts mainnet SegWit, Taproot and legacy", async () => {
    expect(await ok("bc1qmefue372ssa4zffa4n0hqadscqp2myg9utwrtr")).toBe("SegWit (P2WPKH)");
    expect(await ok("bc1p0xlxvlhemja6c4dqv22uapctqupfhlxm9h8z3k2e72q4k9hcz7vqzk5jj0")).toBe("Taproot (P2TR)");
    expect(await ok("1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2")).toBe("Legacy (P2PKH)");
    expect(await ok("3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy")).toBe("Legacy (P2SH)");
  });

  it("is network-aware", async () => {
    const regtest = "bcrt1qac9zasaevp62vwnnuylkm3vsy99gxahlm5n0tz";
    expect(await ok(regtest, "regtest")).toBe("SegWit (P2WPKH)");
    expect(await ok(regtest, "mainnet")).toMatch(/otra red.*mainnet/);
    expect(await ok("bc1qmefue372ssa4zffa4n0hqadscqp2myg9utwrtr", "regtest")).toMatch(/otra red.*regtest/);
    expect(await ok("1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2", "testnet")).toMatch(/otra red/);
  });

  it("rejects bad checksums and unsupported scripts", async () => {
    expect(await ok("bc1qmefue372ssa4zffa4n0hqadscqp2myg9utwrtq")).toMatch(/^error: No es una dirección/);
    expect(await ok("1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN3")).toMatch(/^error: No es una dirección/);
    // witness v1 encoded with bech32 (not bech32m) and a 40-byte program (BIP-173 vector)
    expect(
      await ok("bc1pw508d6qejxtdg4y5r3zarvary0c5xw7kw508d6qejxtdg4y5r3zarvary0c5xw7k7grplx"),
    ).toMatch(/^error/);
    expect(await ok("Bc1qmefue372ssa4zffa4n0hqadscqp2myg9utwrtr")).toMatch(/^error/); // mixed case
    expect(await ok("   ")).toBe("empty");
  });

  it("cleans what people paste", () => {
    expect(clean(" bitcoin:bc1qxyz?amount=0.1 ")).toBe("bc1qxyz");
    expect(clean("bc1qxyz@ln2oc.com")).toBe("bc1qxyz");
  });
});
