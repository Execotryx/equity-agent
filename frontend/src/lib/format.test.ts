import { describe, expect, it } from "vitest";

import { metricText, money, pctChange, percent, seconds } from "./format";

describe("metricText", () => {
  it("formats percent metrics from fractions", () => {
    expect(metricText("net_margin", 0.2764)).toBe("27.6%");
    expect(metricText("dividend_yield", 0.0042)).toBe("0.4%");
  });
  it("formats debt/equity with two decimals and other multiples with one", () => {
    expect(metricText("debt_to_equity", 0.7812)).toBe("0.78");
    expect(metricText("pe_ttm", 34.84)).toBe("34.8");
  });
  it("shows missing and non-meaningful values as an em dash", () => {
    expect(metricText("ev_ebitda", null)).toBe("—");
    expect(metricText("pe_ttm", -12)).toBe("—");
    expect(metricText("revenue_growth", -0.05)).toBe("-5.0%");
  });
});

describe("money", () => {
  it("compacts large values", () => {
    expect(money(4.823e12)).toBe("$4.82T");
    expect(money(391.04e9)).toBe("$391.04B");
    expect(money(-12.5e6)).toBe("-$12.50M");
  });
  it("keeps small values exact and marks other currencies", () => {
    expect(money(212.429)).toBe("$212.43");
    expect(money(1500, "EUR")).toBe("EUR 1,500.00");
    expect(money(null)).toBe("—");
  });
});

describe("other helpers", () => {
  it("formats changes, percents and seconds", () => {
    expect(pctChange(0.123)).toBe("+12%");
    expect(pctChange(-0.081)).toBe("−8%");
    expect(percent(0.62)).toBe("62%");
    expect(seconds(8400)).toBe("8.4 s");
    expect(seconds(undefined)).toBe("—");
  });
});
