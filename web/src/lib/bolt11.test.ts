import { describe, expect, it } from "vitest";
import { invoiceAmountMsat } from "./bolt11";

describe("invoiceAmountMsat", () => {
  it("reads the amount of the human-readable part", () => {
    expect(invoiceAmountMsat("lnbc1m1pxyz", "mainnet")).toBe(100_000_000n); // 0.001 BTC
    expect(invoiceAmountMsat("lnbc2500u1pvjluez", "mainnet")).toBe(250_000_000n); // BOLT 11 example
    expect(invoiceAmountMsat("lnbc1000n1pxyz", "mainnet")).toBe(100_000n); // 100 sats
    expect(invoiceAmountMsat("LNBC10U1PXYZ", "mainnet")).toBe(1_000_000n);
    expect(invoiceAmountMsat("lntb10u1pxyz", "testnet4")).toBe(1_000_000n);
    expect(invoiceAmountMsat("lnbcrt100u1pxyz", "regtest")).toBe(10_000_000n);
  });

  it("rejects other networks, amountless and sub-msat invoices", () => {
    expect(invoiceAmountMsat("lnbcrt100u1pxyz", "mainnet")).toBeNull();
    expect(invoiceAmountMsat("lntb100u1pxyz", "mainnet")).toBeNull();
    expect(invoiceAmountMsat("lnbc1pxyz", "mainnet")).toBeNull();
    expect(invoiceAmountMsat("lnbc1p1pxyz", "mainnet")).toBeNull();
    expect(invoiceAmountMsat("lnbc01u1pxyz", "mainnet")).toBeNull();
    expect(invoiceAmountMsat("garbage", "mainnet")).toBeNull();
  });
});
