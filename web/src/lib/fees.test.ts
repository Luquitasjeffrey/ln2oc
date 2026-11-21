import { describe, expect, it } from "vitest";
import { payoutSat, pct, serviceFeeSat } from "./fees";

describe("fees (mirrors app/fees.py calculate_gross)", () => {
  it("matches the documented 100.000 sats example", () => {
    expect(serviceFeeSat(100_000, 70)).toBe(700);
    expect(payoutSat(100_000, 70, 131)).toBe(99_169);
  });

  it("floors like the integer math in the service", () => {
    // floor(12345 * 9930 / 10000) = floor(12258.585) = 12258
    expect(payoutSat(12_345, 70, 0)).toBe(12_258);
    expect(serviceFeeSat(12_345, 70)).toBe(87);
  });

  it("formats basis points as a percentage", () => {
    expect(pct(70).replace(/\s/g, " ")).toBe("0,7 %");
    expect(pct(125).replace(/\s/g, " ")).toBe("1,25 %");
  });
});
